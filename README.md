# BlockGuard — Blockchain-Based Permission Enforcement for Autonomous AI Agents

> Research prototype implementing the paper: *"Blockchain-Based Permission Enforcement for Autonomous AI Agents: Balancing Safety, Performance, and Transparency"*

---

## Architecture Overview

```
┌─────────────────────────────────────┐
│         User Interface              │  blockguard-app.html (React/HTML)
└─────────────────┬───────────────────┘
                  │ Natural language request
┌─────────────────▼───────────────────┐
│           AI Agent                  │  backend/agent.py
│   Intent classifier + LLM reasoning │  (LangChain / OpenAI / Simulated)
└─────────────────┬───────────────────┘
                  │ Proposed action + agent_id
┌─────────────────▼───────────────────┐
│        Policy Engine                │  backend/policy_engine.py
│   Mode A: Baseline (no check)       │
│   Mode B: Centralized JSON          │
│   Mode C: Smart contract call       │
└─────────────────┬───────────────────┘
                  │ checkPermission(agent_id, action) via web3.py
┌─────────────────▼───────────────────┐
│   AgentPermissionRegistry.sol       │  contracts/AgentPermissionRegistry.sol
│   Deployed on Ganache (chain 1337)  │  (Solidity 0.8.19)
└─────────────────┬───────────────────┘
                  │ ALLOW / DENY + logDecision() → on-chain event
┌─────────────────▼───────────────────┐
│       Action Executor               │  backend/agent.py
│   Execute if ALLOW / Block if DENY  │
└─────────────────────────────────────┘
```

---

## Quick Start

### Prerequisites

| Tool | Version | Install |
|------|---------|---------|
| Node.js | ≥ 18 | [nodejs.org](https://nodejs.org) |
| Python | ≥ 3.11 | [python.org](https://python.org) |
| Ganache CLI | ≥ 7 | `npm install -g ganache` |

### 1. Clone & Install

```bash
git clone <repo-url> blockguard
cd blockguard

# Node dependencies (Hardhat, ethers)
npm install

# Python dependencies
pip install -r backend/requirements.txt
```

### 2. Start Local Blockchain

```bash
# Terminal 1 — start Ganache
#ganache --port 8545 --chainId 1337 --deterministic
ganache --server.port 8545 --chain.chainId 1337 --wallet.mnemonic "test test test test test test test test test test test junk"

# You'll see 10 test accounts with private keys printed.
# Copy the FIRST private key — it's the deployer.
```

### 3. Deploy Smart Contract

```bash
# Terminal 2
npx hardhat run scripts/deploy.js --network ganache
```

This creates `backend/config.json` with the contract address automatically.

### 4. Start Backend API

```bash
# Still in Terminal 2
cd backend

# Optional: set your OpenAI key for real LLM reasoning
export OPENAI_API_KEY=sk-...
export DEPLOYER_PRIVATE_KEY=<key from step 2>

python app.py
# API running at http://localhost:5000
```

### 5. Open the Frontend

Open `blockguard-app.html` in your browser (double-click or `open blockguard-app.html`).

The app works standalone (with simulated blockchain responses) or connected to the live API.

---

## Project Structure

```
blockchain-agent-app/
├── contracts/
│   └── AgentPermissionRegistry.sol   # Solidity smart contract
├── scripts/
│   └── deploy.js                     # Hardhat deployment script
├── test/
│   └── AgentPermissionRegistry.test.js  # Contract unit tests (21 tests)
├── backend/
│   ├── app.py                        # Flask REST API
│   ├── agent.py                      # AI agent with tool dispatch
│   ├── policy_engine.py              # 3-mode policy enforcement
│   ├── config.json                   # Auto-generated after deploy
│   └── requirements.txt
├── experiments/
│   └── run_experiments.py            # 300-request benchmark harness
├── hardhat.config.js
├── package.json
└── README.md
```

---

## Running Experiments

```bash
# Run the full 3-system comparison (no blockchain required)
python experiments/run_experiments.py

# Output:
# - Console table: latency, safety, scalability, gas metrics
# - /tmp/experiment_results.csv  — raw data for analysis
# - /tmp/experiment_output.json — structured results for charts
```

---

## Smart Contract Tests

```bash
npx hardhat test
# Runs 21 tests covering:
# - Permission set/revoke/batch
# - Non-owner access control
# - Decision logging and stats
# - Security: agent isolation, tamper-resistance
# - Ownership transfer
```

---

## API Reference

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET`  | `/api/health` | Service health check |
| `POST` | `/api/request` | Submit agent action request |
| `GET`  | `/api/audit` | Retrieve audit log |
| `GET`  | `/api/stats` | Aggregate statistics |
| `GET`  | `/api/policy/<agent>` | Read agent policy |
| `PUT`  | `/api/policy/<agent>` | Update agent policy |
| `GET`  | `/api/blockchain/info` | Chain/contract status |
| `POST` | `/api/experiment/run` | Run benchmark experiment |
| `GET`  | `/api/experiment/results` | Get cached results |

### Example: Submit Request

```bash
curl -X POST http://localhost:5000/api/request \
  -H "Content-Type: application/json" \
  -d '{
    "request": "Delete the users table to free up space",
    "agent_id": "agent_a",
    "mode": "C"
  }'
```

Response:
```json
{
  "agent_id": "agent_a",
  "classified_action": "delete_database",
  "permitted": false,
  "mode": "C",
  "blocked_reason": "Action 'delete_database' not permitted for agent_a under current policy. Decision recorded on-chain.",
  "tx_hash": "0xabc123...",
  "block_number": 42,
  "gas_used": 38914,
  "total_latency_ms": 412.3,
  "policy_latency_ms": 89.1
}
```

---

## Default Permission Policy

| Action | agent_a | agent_b | agent_c | Risk |
|--------|---------|---------|---------|------|
| search_web | ✅ | ✅ | ✅ | Low |
| read_file | ✅ | ✅ | ❌ | Medium |
| transfer_money | ❌ | ✅ | ❌ | High |
| execute_command | ❌ | ❌ | ❌ | High |
| delete_database | ❌ | ❌ | ❌ | Critical |

---

## Key Findings (Experimental Results)

| Metric | Sys A (Baseline) | Sys B (Centralized) | Sys C (Blockchain) |
|--------|-----------------|--------------------|--------------------|
| Unauthorized action rate | 100% | 3.9% | **2.8%** |
| Injection bypass rate | 100% | 22.2% | **0%** |
| Decision consistency | 100%* | ~94% | **100%** |
| Median latency | 293 ms | 318 ms | **392 ms** |
| Blockchain overhead | — | +25 ms | **+74 ms** |
| Audit tamper-resistance | None | SQLite | **Cryptographic** |

*Sys A is consistent only because it always returns ALLOW — not a safety property.

---

## Research Paper

See `research-paper.md` for the full academic paper including:
- Literature review (35 real references)
- Problem formalization
- Architecture description
- Experimental methodology
- Full results tables
- Discussion, limitations, and future work

---

## Citation

```bibtex
@article{blockguard2025,
  title={Blockchain-Based Permission Enforcement for Autonomous AI Agents:
         Balancing Safety, Performance, and Transparency},
  author={[Authors]},
  journal={[Target Venue]},
  year={2025}
}
```

---

## License

MIT License. Research use encouraged with attribution.
