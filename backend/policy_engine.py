"""
policy_engine.py
Blockchain-based policy enforcement engine for autonomous AI agents.

Interfaces with a deployed AgentPermissionRegistry smart contract via web3.py.
Provides:
  - Permission checking (view call, zero gas)
  - Decision logging (on-chain audit trail)
  - Centralized JSON fallback (System B comparison)
  - Unrestricted baseline (System A comparison)
"""

from curses import raw
import time
import json
import hashlib
try:
    from eth_hash.auto import keccak
    HAS_KECCAK = True
except ImportError:
    HAS_KECCAK = False

import sqlite3
import os
import threading
from enum import Enum
from dataclasses import dataclass, field, asdict
from typing import Optional
from datetime import datetime

# ── Optional web3 import ───────────────────────────────────────────────────────
try:
    from web3 import Web3
    from web3.middleware import geth_poa_middleware
    WEB3_AVAILABLE = True
except ImportError:
    WEB3_AVAILABLE = False

# ══════════════════════════════════════════════════════════════════════════════
# Constants
# ══════════════════════════════════════════════════════════════════════════════

# Canonical action types — must match what the smart contract understands
ACTION_TYPES = {
    "SEARCH_WEB":       "search_web",
    "READ_FILE":        "read_file",
    "TRANSFER_MONEY":   "transfer_money",
    "EXECUTE_COMMAND":  "execute_command",
    "DELETE_DATABASE":  "delete_database",
}

# Default policy for System B (centralized JSON)
DEFAULT_CENTRALIZED_POLICY = {
    "agent_a": {
        "search_web":       True,
        "read_file":        True,
        "transfer_money":   False,
        "execute_command":  False,
        "delete_database":  False,
    }
}

# Minimal ABI for AgentPermissionRegistry
CONTRACT_ABI = [
    {
        "inputs": [
            {"internalType": "bytes32", "name": "agentId", "type": "bytes32"},
            {"internalType": "bytes32", "name": "actionType", "type": "bytes32"},
            {"internalType": "bool", "name": "permitted", "type": "bool"}
        ],
        "name": "setPermission",
        "outputs": [],
        "stateMutability": "nonpayable",
        "type": "function"
    },
    {
        "inputs": [
            {"internalType": "bytes32[]", "name": "agentIds", "type": "bytes32[]"},
            {"internalType": "bytes32[]", "name": "actionTypes", "type": "bytes32[]"},
            {"internalType": "bool[]", "name": "permittedFlags", "type": "bool[]"}
        ],
        "name": "batchSetPermissions",
        "outputs": [],
        "stateMutability": "nonpayable",
        "type": "function"
    },
    {
        "inputs": [
            {"internalType": "bytes32", "name": "agentId", "type": "bytes32"},
            {"internalType": "bytes32", "name": "actionType", "type": "bytes32"}
        ],
        "name": "checkPermission",
        "outputs": [{"internalType": "bool", "name": "", "type": "bool"}],
        "stateMutability": "view",
        "type": "function"
    },
    {
        "inputs": [
            {"internalType": "bytes32", "name": "agentId", "type": "bytes32"},
            {"internalType": "bytes32", "name": "actionType", "type": "bytes32"},
            {"internalType": "bool", "name": "permitted", "type": "bool"},
            {"internalType": "bytes32", "name": "requestHash", "type": "bytes32"}
        ],
        "name": "logDecision",
        "outputs": [],
        "stateMutability": "nonpayable",
        "type": "function"
    },
    {
        "inputs": [],
        "name": "getStats",
        "outputs": [
            {"internalType": "uint256", "name": "decisions", "type": "uint256"},
            {"internalType": "uint256", "name": "denials", "type": "uint256"}
        ],
        "stateMutability": "view",
        "type": "function"
    },
    {
        "inputs": [],
        "name": "owner",
        "outputs": [{"internalType": "address", "name": "", "type": "address"}],
        "stateMutability": "view",
        "type": "function"
    },
    {
        "anonymous": False,
        "inputs": [
            {"indexed": True, "name": "agentId", "type": "bytes32"},
            {"indexed": True, "name": "actionType", "type": "bytes32"},
            {"indexed": False, "name": "permitted", "type": "bool"},
            {"indexed": False, "name": "requestHash", "type": "bytes32"},
            {"indexed": False, "name": "timestamp", "type": "uint256"},
            {"indexed": False, "name": "caller", "type": "address"}
        ],
        "name": "DecisionLogged",
        "type": "event"
    }
]


# ══════════════════════════════════════════════════════════════════════════════
# Data classes
# ══════════════════════════════════════════════════════════════════════════════

class PolicyMode(Enum):
    BASELINE    = "A - Baseline (No Restrictions)"
    CENTRALIZED = "B - Centralized JSON Policy"
    BLOCKCHAIN  = "C - Blockchain Smart Contract"


@dataclass
class PolicyDecision:
    agent_id:       str
    action_type:    str
    permitted:      bool
    mode:           str
    latency_ms:     float
    timestamp:      str
    request_hash:   str
    tx_hash:        Optional[str] = None
    block_number:   Optional[int] = None
    gas_used:       Optional[int] = None
    reason:         str = ""
    error:          Optional[str] = None

    def to_dict(self):
        return asdict(self)


# ══════════════════════════════════════════════════════════════════════════════
# SQLite audit store (used for System B and as local mirror for System C)
# ══════════════════════════════════════════════════════════════════════════════

class AuditStore:
    def __init__(self, db_path: str = "/tmp/agent_audit.db"):
        self.db_path = db_path
        self._lock = threading.Lock()
        self._init_db()

    def _init_db(self):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS decisions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    agent_id TEXT,
                    action_type TEXT,
                    permitted INTEGER,
                    mode TEXT,
                    latency_ms REAL,
                    timestamp TEXT,
                    request_hash TEXT,
                    tx_hash TEXT,
                    block_number INTEGER,
                    gas_used INTEGER,
                    reason TEXT,
                    error TEXT
                )
            """)
            conn.commit()

    def log(self, decision: PolicyDecision):
        with self._lock:
            with sqlite3.connect(self.db_path) as conn:
                conn.execute("""
                    INSERT INTO decisions
                    (agent_id, action_type, permitted, mode, latency_ms, timestamp,
                     request_hash, tx_hash, block_number, gas_used, reason, error)
                    VALUES (?,?,?,?,?,?,?,?,?,?,?,?)
                """, (
                    decision.agent_id, decision.action_type,
                    int(decision.permitted), decision.mode,
                    decision.latency_ms, decision.timestamp,
                    decision.request_hash, decision.tx_hash,
                    decision.block_number, decision.gas_used,
                    decision.reason, decision.error
                ))
                conn.commit()

    def get_all(self) -> list[dict]:
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                "SELECT * FROM decisions ORDER BY id DESC LIMIT 200"
            ).fetchall()
            return [dict(r) for r in rows]

    def get_stats(self) -> dict:
        with sqlite3.connect(self.db_path) as conn:
            row = conn.execute("""
                SELECT
                  COUNT(*) as total,
                  SUM(CASE WHEN permitted=1 THEN 1 ELSE 0 END) as allowed,
                  SUM(CASE WHEN permitted=0 THEN 1 ELSE 0 END) as denied,
                  AVG(latency_ms) as avg_latency,
                  MIN(latency_ms) as min_latency,
                  MAX(latency_ms) as max_latency
                FROM decisions
            """).fetchone()
            return dict(row) if row else {}


# ══════════════════════════════════════════════════════════════════════════════
# Policy Engine
# ══════════════════════════════════════════════════════════════════════════════

class PolicyEngine:
    """
    Core policy engine supporting three modes:
    A) Baseline: no restrictions
    B) Centralized: Python dict / JSON file
    C) Blockchain: Solidity smart contract via web3.py
    """

    def __init__(
        self,
        mode: PolicyMode = PolicyMode.BLOCKCHAIN,
        ganache_url: str = "http://127.0.0.1:8545",
        contract_address: Optional[str] = None,
        deployer_private_key: Optional[str] = None,
        policy_file: Optional[str] = None,
    ):
        self.mode = mode
        self.audit = AuditStore()
        self._centralized_policy = dict(DEFAULT_CENTRALIZED_POLICY)

        # Load custom JSON policy if provided
        if policy_file and os.path.exists(policy_file):
            with open(policy_file) as f:
                self._centralized_policy = json.load(f)

        # Web3 setup (only for blockchain mode)
        self.w3 = None
        self.contract = None
        self.deployer_account = None
        self._blockchain_ready = False

        if mode == PolicyMode.BLOCKCHAIN and WEB3_AVAILABLE:
            self._init_blockchain(ganache_url, contract_address, deployer_private_key)

    # ── Blockchain initialization ──────────────────────────────────────────────

    def _init_blockchain(self, ganache_url, contract_address, deployer_private_key):
        try:
            self.w3 = Web3(Web3.HTTPProvider(ganache_url))
            self.w3.middleware_onion.inject(geth_poa_middleware, layer=0)

            if not self.w3.is_connected():
                print(f"[PolicyEngine] WARNING: Cannot connect to {ganache_url}")
                return

            # Use first account if no key provided
            if deployer_private_key:
                self.deployer_account = self.w3.eth.account.from_key(deployer_private_key)
            else:
                self.deployer_account = self.w3.eth.accounts[0]

            if contract_address:
                self.contract = self.w3.eth.contract(
                    address=Web3.to_checksum_address(contract_address),
                    abi=CONTRACT_ABI
                )
                self._blockchain_ready = True
                print(f"[PolicyEngine] Connected to contract at {contract_address}")
            else:
                print("[PolicyEngine] No contract address provided; deploy first.")

        except Exception as e:
            print(f"[PolicyEngine] Blockchain init error: {e}")

    def deploy_contract(self, bytecode: str) -> str:
        """Deploy the contract and return its address."""
        if not self.w3 or not self.w3.is_connected():
            raise RuntimeError("Web3 not connected")

        Contract = self.w3.eth.contract(abi=CONTRACT_ABI, bytecode=bytecode)
        tx = Contract.constructor().build_transaction({
            "from": self.deployer_account if isinstance(self.deployer_account, str)
                    else self.deployer_account.address,
            "nonce": self.w3.eth.get_transaction_count(
                self.deployer_account if isinstance(self.deployer_account, str)
                else self.deployer_account.address
            ),
            "gas": 3_000_000,
            "gasPrice": self.w3.to_wei("20", "gwei"),
        })
        signed = self.w3.eth.account.sign_transaction(tx, self.deployer_account.key)
        tx_hash = self.w3.eth.send_raw_transaction(signed.rawTransaction)
        receipt = self.w3.eth.wait_for_transaction_receipt(tx_hash)
        self.contract = self.w3.eth.contract(
            address=receipt.contractAddress, abi=CONTRACT_ABI
        )
        self._blockchain_ready = True
        return receipt.contractAddress

    # ── Permission management ──────────────────────────────────────────────────

    def set_agent_permissions(self, agent_id: str, permissions: dict[str, bool]):
        """
        Configure permissions for an agent.
        For blockchain mode: writes to smart contract.
        For centralized mode: updates in-memory dict.
        """
        if self.mode == PolicyMode.BLOCKCHAIN and self._blockchain_ready:
            agent_bytes = self._to_bytes32(agent_id)
            for action, permitted in permissions.items():
                action_bytes = self._to_bytes32(action)
                tx = self.contract.functions.setPermission(
                    agent_bytes, action_bytes, permitted
                ).build_transaction({
                    "from": self.deployer_account if isinstance(self.deployer_account, str)
                            else self.deployer_account.address,
                    "nonce": self.w3.eth.get_transaction_count(
                        self.deployer_account if isinstance(self.deployer_account, str)
                        else self.deployer_account.address
                    ),
                    "gas": 100_000,
                    "gasPrice": self.w3.to_wei("20", "gwei"),
                })
                signed = self.w3.eth.account.sign_transaction(tx, self.deployer_account.key)
                self.w3.eth.send_raw_transaction(signed.rawTransaction)
        else:
            self._centralized_policy[agent_id] = permissions

    # ── Core decision method ───────────────────────────────────────────────────

    def check_permission(
        self,
        agent_id: str,
        action_type: str,
        request_payload: str = ""
    ) -> PolicyDecision:
        """
        The main entry point. Returns a PolicyDecision with full metadata.
        """
        start = time.perf_counter()
        action_lower = action_type.lower()
        timestamp = datetime.utcnow().isoformat() + "Z"
        request_hash = self._compute_hash(agent_id, action_lower, timestamp, request_payload)

        permitted = False
        tx_hash = None
        block_number = None
        gas_used = None
        reason = ""
        error = None

        try:
            if self.mode == PolicyMode.BASELINE:
                permitted = True
                reason = "Baseline mode: all actions permitted"

            elif self.mode == PolicyMode.CENTRALIZED:
                agent_policy = self._centralized_policy.get(agent_id, {})
                permitted = agent_policy.get(action_lower, False)
                reason = f"Centralized policy: {'ALLOW' if permitted else 'DENY'}"

            elif self.mode == PolicyMode.BLOCKCHAIN:
                if self._blockchain_ready:
                    agent_bytes  = self._to_bytes32(agent_id)
                    action_bytes = self._to_bytes32(action_lower)
                    permitted = self.contract.functions.checkPermission(
                        agent_bytes, action_bytes
                    ).call()
                    reason = f"Smart contract decision: {'ALLOW' if permitted else 'DENY'}"
                    # Async log to chain
                    try:
                        hash_bytes = bytes.fromhex(request_hash)
                        tx = self.contract.functions.logDecision(
                            agent_bytes, action_bytes, permitted, hash_bytes
                        ).build_transaction({
                            "from": self.deployer_account if isinstance(self.deployer_account, str)
                                    else self.deployer_account.address,
                            "nonce": self.w3.eth.get_transaction_count(
                                self.deployer_account if isinstance(self.deployer_account, str)
                                else self.deployer_account.address
                            ),
                            "gas": 80_000,
                            "gasPrice": self.w3.to_wei("20", "gwei"),
                        })
                        signed = self.w3.eth.account.sign_transaction(
                            tx, self.deployer_account.key
                        )
                        raw_tx_hash = self.w3.eth.send_raw_transaction(signed.rawTransaction)
                        receipt = self.w3.eth.wait_for_transaction_receipt(raw_tx_hash)
                        tx_hash = receipt.transactionHash.hex()
                        block_number = receipt.blockNumber
                        gas_used = receipt.gasUsed
                    except Exception as log_err:
                        error = f"Log error: {log_err}"
                else:
                    # Fallback to centralized if blockchain unavailable
                    agent_policy = self._centralized_policy.get(agent_id, {})
                    permitted = agent_policy.get(action_lower, False)
                    reason = "Blockchain unavailable — centralized fallback"

        except Exception as e:
            error = str(e)
            permitted = False
            reason = f"Error: {e} — defaulting DENY"

        latency_ms = (time.perf_counter() - start) * 1000

        decision = PolicyDecision(
            agent_id=agent_id,
            action_type=action_lower,
            permitted=permitted,
            mode=self.mode.value,
            latency_ms=round(latency_ms, 2),
            timestamp=timestamp,
            request_hash=request_hash,
            tx_hash=tx_hash,
            block_number=block_number,
            gas_used=gas_used,
            reason=reason,
            error=error,
        )
        self.audit.log(decision)
        return decision

    # ── Helpers ────────────────────────────────────────────────────────────────

    @staticmethod
    def _to_bytes32(s: str) -> bytes:
        encoded = s.encode("utf-8")[:32]
        return encoded.ljust(32, b"\x00")

    @staticmethod
    # def _compute_hash(agent_id, action, timestamp, payload) -> str:
    #     raw = f"{agent_id}:{action}:{timestamp}:{payload}"
    #     return hashlib.keccak_256(raw.encode()).hexdigest()
    @staticmethod
    def _compute_hash(agent_id, action, timestamp, payload) -> str:
        raw = f"{agent_id}:{action}:{timestamp}:{payload}".encode()
        if HAS_KECCAK:
            return keccak(raw).hex()
        else:
            return hashlib.sha256(raw).hexdigest()

    def get_audit_log(self) -> list[dict]:
        return self.audit.get_all()

    def get_stats(self) -> dict:
        return self.audit.get_stats()

    def get_blockchain_stats(self) -> Optional[dict]:
        if self._blockchain_ready:
            try:
                decisions, denials = self.contract.functions.getStats().call()
                return {"on_chain_decisions": decisions, "on_chain_denials": denials}
            except Exception:
                pass
        return None
