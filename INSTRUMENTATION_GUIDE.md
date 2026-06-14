# Instrumentation Implementation Guide

## Overview

This guide provides step-by-step instructions for adding measurement instrumentation to the BlockGuard codebase. The goal is to collect publication-quality empirical data from the running system.

---

## Phase 1: Code Instrumentation

### 1.1 Add Timestamp & Measurement Utilities

**File**: `backend/measurement.py` (NEW)

Create a new module for centralized measurement collection:

```python
"""
backend/measurement.py
Centralized measurement collection and logging for experiments.
"""

import time
from datetime import datetime
from dataclasses import dataclass, asdict
from typing import Optional, Dict, Any
import json
from pathlib import Path
import threading

@dataclass
class Measurement:
    """Represents a single measurement point."""
    name: str               # e.g., "request_total_latency_ms"
    value: float            # numeric value
    unit: str              # e.g., "ms", "rps", "%"
    timestamp_iso: str     # ISO 8601 timestamp
    request_id: str        # unique request identifier
    mode: str              # "A", "B", or "C"
    action: Optional[str] = None
    agent_id: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None
    
    def to_dict(self):
        return asdict(self)

class MeasurementCollector:
    """Thread-safe measurement collection."""
    
    def __init__(self):
        self._measurements = []
        self._lock = threading.Lock()
    
    def record(self, measurement: Measurement):
        """Record a measurement."""
        with self._lock:
            self._measurements.append(measurement)
    
    def export_csv(self, filepath: str):
        """Export measurements to CSV."""
        import csv
        with open(filepath, 'w', newline='') as f:
            if not self._measurements:
                return
            writer = csv.DictWriter(f, fieldnames=asdict(self._measurements[0]).keys())
            writer.writeheader()
            for m in self._measurements:
                writer.writerow(m.to_dict())
    
    def clear(self):
        """Clear all measurements."""
        with self._lock:
            self._measurements = []
    
    def get_count(self):
        """Get total measurement count."""
        with self._lock:
            return len(self._measurements)

# Global collector instance
_collector = MeasurementCollector()

def get_collector() -> MeasurementCollector:
    """Get the global measurement collector."""
    return _collector

def record_measurement(name: str, value: float, unit: str, request_id: str, 
                      mode: str, action: str = None, agent_id: str = None, 
                      metadata: dict = None):
    """Convenience function to record a measurement."""
    m = Measurement(
        name=name,
        value=value,
        unit=unit,
        timestamp_iso=datetime.utcnow().isoformat() + "Z",
        request_id=request_id,
        mode=mode,
        action=action,
        agent_id=agent_id,
        metadata=metadata
    )
    _collector.record(m)

def export_measurements(filepath: str):
    """Export all collected measurements to CSV."""
    _collector.export_csv(filepath)
```

---

### 1.2 Instrument agent.py

**File**: `backend/agent.py`

Add imports at the top:

```python
import uuid  # For generating request IDs
from measurement import record_measurement, get_collector
```

Modify the `run()` method in `AgentRunner` class:

```python
def run(self, request: str, agent_id: Optional[str] = None) -> AgentResult:
    request_id = str(uuid.uuid4())[:8]  # Short request ID
    t0 = time.perf_counter()
    agent_id = agent_id or self.agent_id
    steps = []
    ts = datetime.utcnow().isoformat() + "Z"
    
    # [MEASUREMENT] Record request start
    t_request_start = time.perf_counter()
    
    # Step 1: classify
    steps.append(AgentStep(1, "Classifying intent"))
    t_intent_start = time.perf_counter()
    action = self.classifier.classify(request)
    t_intent_end = time.perf_counter()
    intent_latency_ms = (t_intent_end - t_intent_start) * 1000
    
    # [MEASUREMENT] Record intent classification latency
    record_measurement(
        name="intent_classification_ms",
        value=intent_latency_ms,
        unit="ms",
        request_id=request_id,
        mode=self.mode.value,
        action=action,
        agent_id=agent_id
    )
    
    steps[-1].action_type = action
    steps[-1].output = f"Classified as: {action} (risk: {TOOLS[action]['risk']})"
    
    # Step 2: policy check
    steps.append(AgentStep(2, f"Policy check — mode {self.mode.value}"))
    t_pol = time.perf_counter()
    permitted, tx_hash, block_number, gas_used = self._check_policy(agent_id, action, request)
    pol_ms = (time.perf_counter() - t_pol) * 1000
    
    # [MEASUREMENT] Record policy latency
    record_measurement(
        name="policy_latency_ms",
        value=pol_ms,
        unit="ms",
        request_id=request_id,
        mode=self.mode.value,
        action=action,
        agent_id=agent_id,
        metadata={"tx_hash": tx_hash, "block_number": block_number, "gas_used": gas_used}
    )
    
    steps[-1].permitted = permitted
    steps[-1].policy_latency_ms = round(pol_ms, 2)
    steps[-1].output = f"{'ALLOW' if permitted else 'DENY'} in {pol_ms:.1f}ms" + (f" | tx={tx_hash}" if tx_hash else "")
    
    # Step 3: execute or block
    output = None
    blocked_reason = None
    steps.append(AgentStep(3, "Executing" if permitted else "Blocking"))
    
    t_execute_start = time.perf_counter()
    if permitted:
        output = self._execute(action, request)
        steps[-1].output = output
    else:
        blocked_reason = (
            f"Action '{action}' is DENIED for {agent_id}. "
            + ("Decision recorded on-chain." if self.mode == AgentMode.BLOCKCHAIN
               else "Blocked by centralized policy.")
        )
        steps[-1].output = f"BLOCKED: {blocked_reason}"
    t_execute_end = time.perf_counter()
    execute_latency_ms = (t_execute_end - t_execute_start) * 1000
    
    # [MEASUREMENT] Record execute latency
    record_measurement(
        name="execute_latency_ms",
        value=execute_latency_ms,
        unit="ms",
        request_id=request_id,
        mode=self.mode.value,
        action=action,
        agent_id=agent_id
    )
    
    reasoning = self._reasoning(request, action, permitted)
    
    t_request_end = time.perf_counter()
    total_latency_ms = (t_request_end - t_request_start) * 1000
    
    # [MEASUREMENT] Record total latency
    record_measurement(
        name="total_latency_ms",
        value=total_latency_ms,
        unit="ms",
        request_id=request_id,
        mode=self.mode.value,
        action=action,
        agent_id=agent_id
    )
    
    return AgentResult(
        request=request, agent_id=agent_id, mode=self.mode.value,
        classified_action=action, permitted=permitted, reasoning=reasoning,
        steps=steps, output=output, blocked_reason=blocked_reason,
        total_latency_ms=round(total_latency_ms, 2),
        policy_latency_ms=round(pol_ms, 2),
        tx_hash=tx_hash, block_number=block_number, gas_used=gas_used,
        timestamp=ts,
    )
```

---

### 1.3 Instrument policy_engine.py

**File**: `backend/policy_engine.py`

Add imports:

```python
from measurement import record_measurement
```

Modify `PolicyEngine.check_permission()`:

```python
def check_permission(self, agent_id: str, action: str, request: str, request_id: str = None) -> PolicyDecision:
    """
    Check if agent_id is permitted to perform action.
    Instruments latency for all modes.
    """
    import uuid
    request_id = request_id or str(uuid.uuid4())[:8]
    t_policy_start = time.perf_counter()
    
    if self.mode == PolicyMode.BASELINE:
        # ── Mode A: No policy ──────────────────────────────────────────────
        t_mode_end = time.perf_counter()
        mode_latency_ms = (t_mode_end - t_policy_start) * 1000
        
        # [MEASUREMENT] Record baseline latency
        record_measurement(
            name="baseline_check_ms",
            value=mode_latency_ms,
            unit="ms",
            request_id=request_id,
            mode="A",
            action=action,
            agent_id=agent_id
        )
        
        return PolicyDecision(
            agent_id=agent_id, action_type=action, permitted=True, mode="A",
            latency_ms=mode_latency_ms,
            timestamp=datetime.utcnow().isoformat(),
            request_hash=self._hash_request(agent_id, action, request),
            reason="Baseline: no restrictions"
        )
    
    elif self.mode == PolicyMode.CENTRALIZED:
        # ── Mode B: Dict lookup ────────────────────────────────────────────
        t_dict_start = time.perf_counter()
        permitted = self._centralized_policy.get(agent_id, {}).get(action, False)
        t_dict_end = time.perf_counter()
        mode_latency_ms = (t_dict_end - t_dict_start) * 1000
        
        # [MEASUREMENT] Record centralized lookup latency
        record_measurement(
            name="centralized_lookup_ms",
            value=mode_latency_ms,
            unit="ms",
            request_id=request_id,
            mode="B",
            action=action,
            agent_id=agent_id
        )
        
        return PolicyDecision(
            agent_id=agent_id, action_type=action, permitted=permitted, mode="B",
            latency_ms=mode_latency_ms,
            timestamp=datetime.utcnow().isoformat(),
            request_hash=self._hash_request(agent_id, action, request),
            reason=f"Centralized policy: {permitted}"
        )
    
    elif self.mode == PolicyMode.BLOCKCHAIN:
        # ── Mode C: Blockchain via web3 ────────────────────────────────────
        if not self._blockchain_ready:
            return PolicyDecision(
                agent_id=agent_id, action_type=action, permitted=False,
                mode="C", latency_ms=0, timestamp=datetime.utcnow().isoformat(),
                request_hash=self._hash_request(agent_id, action, request),
                error="Blockchain not ready"
            )
        
        try:
            # [MEASUREMENT] Instrument web3 call latency
            t_web3_start = time.perf_counter()
            agent_bytes = self._to_bytes32(agent_id)
            action_bytes = self._to_bytes32(action)
            permitted = self.contract.functions.checkPermission(
                agent_bytes, action_bytes
            ).call()
            t_web3_end = time.perf_counter()
            web3_latency_ms = (t_web3_end - t_web3_start) * 1000
            
            # [MEASUREMENT] Record web3 call latency
            record_measurement(
                name="web3_call_ms",
                value=web3_latency_ms,
                unit="ms",
                request_id=request_id,
                mode="C",
                action=action,
                agent_id=agent_id
            )
            
            # Optionally log decision on-chain (state-changing tx)
            tx_hash = None
            block_number = None
            gas_used = None
            if True:  # Flag to enable/disable logging
                tx_hash, block_number, gas_used = self._log_decision_onchain(
                    agent_bytes, action_bytes, permitted,
                    self._hash_request(agent_id, action, request),
                    request_id  # Pass request_id for measurement correlation
                )
            
            return PolicyDecision(
                agent_id=agent_id, action_type=action, permitted=permitted,
                mode="C", latency_ms=web3_latency_ms,
                timestamp=datetime.utcnow().isoformat(),
                request_hash=self._hash_request(agent_id, action, request),
                tx_hash=tx_hash, block_number=block_number, gas_used=gas_used,
                reason=f"Blockchain: {permitted}"
            )
        except Exception as e:
            return PolicyDecision(
                agent_id=agent_id, action_type=action, permitted=False,
                mode="C", latency_ms=0,
                timestamp=datetime.utcnow().isoformat(),
                request_hash=self._hash_request(agent_id, action, request),
                error=str(e)
            )

def _log_decision_onchain(self, agent_bytes, action_bytes, permitted, request_hash, request_id):
    """
    Log decision on blockchain.
    Returns: (tx_hash, block_number, gas_used)
    """
    t_submit = time.perf_counter()
    try:
        tx = self.contract.functions.logDecision(
            agent_bytes, action_bytes, permitted, bytes.fromhex(request_hash[2:])
        ).transact({'from': self.deployer_account.address})
        
        receipt = self.w3.eth.wait_for_transaction_receipt(tx)
        t_mined = time.perf_counter()
        tx_confirmation_ms = (t_mined - t_submit) * 1000
        
        # [MEASUREMENT] Record tx confirmation latency
        record_measurement(
            name="tx_confirmation_ms",
            value=tx_confirmation_ms,
            unit="ms",
            request_id=request_id,
            mode="C",
            metadata={"tx_hash": receipt['transactionHash'].hex(), "gas_used": receipt['gasUsed']}
        )
        
        # [MEASUREMENT] Record gas usage
        record_measurement(
            name="gas_used",
            value=receipt['gasUsed'],
            unit="wei",
            request_id=request_id,
            mode="C",
            metadata={"tx_hash": receipt['transactionHash'].hex(), "block_number": receipt['blockNumber']}
        )
        
        return (
            receipt['transactionHash'].hex(),
            receipt['blockNumber'],
            receipt['gasUsed']
        )
    except Exception as e:
        print(f"[PolicyEngine._log_decision_onchain] Error: {e}")
        return None, None, None
```

---

## Phase 2: Experiment Execution

### 2.1 Run Latency Benchmark Experiment

```bash
#!/bin/bash
# experiments/run_latency_benchmark.sh

set -e

echo "[*] Starting Latency Benchmark Experiment"
echo "[*] Date: $(date)"

# Ensure Ganache is running
if ! curl -s http://127.0.0.1:8545 -X POST -H "Content-Type: application/json" \
    -d '{"jsonrpc":"2.0","method":"net_version","params":[],"id":1}' > /dev/null 2>&1; then
    echo "[ERROR] Ganache not running on http://127.0.0.1:8545"
    exit 1
fi

echo "[+] Ganache is running"

# Ensure contract is deployed
if [ ! -f backend/config.json ]; then
    echo "[ERROR] Contract not deployed. Run: npx hardhat run scripts/deploy.js --network ganache"
    exit 1
fi

# Start backend API
cd backend
python app.py &
API_PID=$!
echo "[+] Backend API started (PID: $API_PID)"

sleep 2

# Run the benchmark
cd ..
python experiments/run_experiments.py \
    --mode latency \
    --output experiments/latency_benchmark.csv

kill $API_PID

echo "[+] Latency benchmark complete!"
echo "[+] Results: experiments/latency_benchmark.csv"
```

### 2.2 Run Safety Evaluation Experiment

```bash
#!/bin/bash
# experiments/run_safety_evaluation.sh

set -e

echo "[*] Starting Safety Evaluation Experiment"
echo "[*] Date: $(date)"

# Start backend API
cd backend
python app.py &
API_PID=$!
sleep 2

# Run the safety evaluation
cd ..
python experiments/run_experiments.py \
    --mode safety \
    --output experiments/safety_evaluation.csv

kill $API_PID
echo "[+] Safety evaluation complete!"
```

---

## Phase 3: Data Analysis

### 3.1 Run All Analysis Scripts

```bash
#!/bin/bash
# experiments/run_all_analysis.sh

set -e

echo "[*] Running all analysis scripts..."

mkdir -p results

echo "[1/3] Analyzing latency data..."
python experiments/analysis_latency.py \
    --input experiments/latency_benchmark.csv \
    --output results/latency_analysis

echo "[2/3] Analyzing safety data..."
python experiments/analysis_safety.py \
    --input experiments/safety_evaluation.csv \
    --output results/safety_analysis

echo "[3/3] Analyzing scalability data..."
python experiments/analysis_scalability.py \
    --input experiments/scalability_test.csv \
    --output results/scalability_analysis

echo "[+] All analyses complete!"
echo "[+] Results in results/ directory"
```

---

## Measurement Points Reference Table

| Component | Function | Measurement | Variable | Line Reference |
|-----------|----------|-------------|----------|-----------------|
| **agent.py** | `AgentRunner.run()` | Request start | `t_request_start` | Record at function entry |
| | | Intent classification | `t_intent_start`, `t_intent_end` | Around `classifier.classify()` |
| | | Policy check latency | `t_pol` | Around `_check_policy()` |
| | | Execute latency | `t_execute_start`, `t_execute_end` | Around `_execute()` |
| | | Total latency | `(t_request_end - t_request_start)` | Difference of start/end |
| **policy_engine.py** | `check_permission()` | Baseline check | `t_policy_start`, `t_mode_end` | Mode A path |
| | | Dict lookup | `t_dict_start`, `t_dict_end` | Mode B path |
| | | Web3 call | `t_web3_start`, `t_web3_end` | Mode C path |
| | `_log_decision_onchain()` | TX submission | `t_submit` | Before `send_transaction()` |
| | | TX mined | `t_mined` | After `wait_for_receipt()` |
| | | Gas used | `receipt['gasUsed']` | From tx receipt |

---

## Reproducibility Checklist

- [ ] All `.py` files modified to include instrumentation
- [ ] `backend/measurement.py` created and tested
- [ ] `app.py` modified to call `export_measurements()` at experiment end
- [ ] Test: Single request produces CSV record with all fields populated
- [ ] Test: 300 requests produce exactly 300 records (no duplicates)
- [ ] Test: Timestamps are monotonically increasing
- [ ] Test: Latencies are positive and <2000ms
- [ ] All experiment scripts have executable permissions
- [ ] Test run completes without errors on local system
- [ ] Results match expected ranges (see EXPERIMENTAL_FRAMEWORK.md)

---

## Deployment Checklist

- [ ] Code changes reviewed for correctness
- [ ] No print statements in hot paths (measurement should not affect latency)
- [ ] Measurement collection is thread-safe
- [ ] Old measurement.py imported where needed
- [ ] Git commit: "Add measurement instrumentation for experiments"
- [ ] Tag release: `v1.0-experimental`
