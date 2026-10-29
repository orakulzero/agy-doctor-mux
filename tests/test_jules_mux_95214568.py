import pytest
from typing import Any

from agy_doctor_mux.mux import HookEntry, HookMultiplexer, create_default_golden_stack_mux, measure_mux_speedup

def test_dispatch_stop_loop_breaker():
    mux = HookMultiplexer(max_stop_continuations=2)
    
    def deny_handler(payload: dict[str, Any]) -> dict[str, Any]:
        return {"decision": "deny", "reason": "Test deny"}

    mux.register(HookEntry(
        name="stopper",
        event="Stop",
        priority=10,
        handler=deny_handler
    ))
    
    session_id = "test_sess"
    payload = {"session_id": session_id}
    
    # First dispatch - deny (count=1)
    res = mux.dispatch("Stop", payload)
    assert res["decision"] == "deny"
    assert res["blocked_by"] == "stopper"
    
    # Second dispatch - deny (count=2)
    res = mux.dispatch("Stop", payload)
    assert res["decision"] == "deny"
    
    # Third dispatch - count=3 (> max_stop_continuations=2) -> allow (loop breaker)
    res = mux.dispatch("Stop", payload)
    assert res["decision"] == "allow"
    assert res.get("loop_breaker_triggered") is True
    assert res["reason"] == "Max consecutive Stop continuations exceeded; breaking infinite loop."
    
    # Fourth dispatch - counter was reset, so should deny again (count=1)
    res = mux.dispatch("Stop", payload)
    assert res["decision"] == "deny"
    assert res.get("loop_breaker_triggered") is None or res.get("loop_breaker_triggered") is False

def test_dispatch_stop_allow_resets_counter():
    mux = HookMultiplexer(max_stop_continuations=2)
    
    deny_mode = True
    def conditional_handler(payload: dict[str, Any]) -> dict[str, Any]:
        if deny_mode:
            return {"decision": "deny"}
        return {"decision": "allow"}
        
    mux.register(HookEntry(
        name="cond_stopper",
        event="Stop",
        priority=10,
        handler=conditional_handler
    ))
    
    payload = {"session_id": "sess2"}
    
    # Deny (count=1)
    mux.dispatch("Stop", payload)
    # Deny (count=2)
    mux.dispatch("Stop", payload)
    
    # Switch to allow
    deny_mode = False
    res = mux.dispatch("Stop", payload)
    assert res["decision"] == "allow"
    assert res.get("loop_breaker_triggered") is False
    
    # Switch back to deny
    deny_mode = True
    # If counter was reset on allow, this should be deny, not loop breaker
    res = mux.dispatch("Stop", payload)
    assert res["decision"] == "deny"

def test_standard_event_fail_fast():
    mux = HookMultiplexer()
    
    mux.register(HookEntry(
        name="allow_hook",
        event="PreToolUse",
        priority=10,
        handler=lambda p: {"decision": "allow"}
    ))
    mux.register(HookEntry(
        name="deny_hook",
        event="PreToolUse",
        priority=20,
        handler=lambda p: {"decision": "deny", "reason": "blocked"}
    ))
    mux.register(HookEntry(
        name="unreached_hook",
        event="PreToolUse",
        priority=30,
        handler=lambda p: {"decision": "deny"}
    ))
    
    res = mux.dispatch("PreToolUse", {})
    assert res["decision"] == "deny"
    assert res["blocked_by"] == "deny_hook"
    assert res["executed_hooks"] == ["allow_hook", "deny_hook"]
    assert "unreached_hook" not in res["executed_hooks"]

def test_deferred_hooks():
    mux = HookMultiplexer()
    
    mux.register(HookEntry(
        name="active_allow",
        event="Stop",
        priority=10,
        handler=lambda p: {"decision": "allow"}
    ))
    mux.register(HookEntry(
        name="deferred_hook",
        event="Stop",
        priority=20,
        handler=lambda p: {"decision": "allow"},
        deferred_until_allow=True
    ))
    
    res = mux.dispatch("Stop", {})
    assert res["decision"] == "allow"
    assert res["executed_hooks"] == ["active_allow", "deferred_hook"]
    
    # What if active denies? Deferred shouldn't run.
    mux2 = HookMultiplexer()
    mux2.register(HookEntry(
        name="active_deny",
        event="Stop",
        priority=10,
        handler=lambda p: {"decision": "deny"}
    ))
    mux2.register(HookEntry(
        name="deferred_hook",
        event="Stop",
        priority=20,
        handler=lambda p: {"decision": "allow"},
        deferred_until_allow=True
    ))
    
    res2 = mux2.dispatch("Stop", {})
    assert res2["decision"] == "deny"
    assert res2["executed_hooks"] == ["active_deny"]

def test_no_hooks():
    mux = HookMultiplexer()
    res = mux.dispatch("UnknownEvent", {})
    assert res["decision"] == "allow"
    assert res["executed_hooks"] == []
    
    res_stop = mux.dispatch("Stop", {})
    assert res_stop["decision"] == "allow"
    assert res_stop["executed_hooks"] == []

def test_default_golden_stack():
    mux = create_default_golden_stack_mux()
    assert isinstance(mux, HookMultiplexer)
    
    res = mux.dispatch("Stop", {})
    assert res["decision"] == "allow"
    assert "P10_context_guard" in res["executed_hooks"]
    assert "P20_memory_consolidator" in res["executed_hooks"]

def test_measure_mux_speedup():
    res = measure_mux_speedup(iterations=1)
    assert "in_process_avg_ms" in res
    assert "subprocess_avg_ms" in res
    assert "speedup_factor" in res
    assert res["iterations"] == 1
