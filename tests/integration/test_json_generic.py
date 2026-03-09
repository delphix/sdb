#
# Copyright 2025 CoreWeave
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#
"""
Integration tests for JSON output mode (--json) using regression crash dumps.

These tests verify that:
1. Every command that succeeds in normal mode also produces valid JSON.
2. Every JSON entry has the required "type" and "value" fields.
3. Error commands produce a JSON {"error": ...} response.
4. The JSON output is stable across runs (regression baselines).
"""

import json
from typing import Any

import pytest
from tests.integration.infra import (
    get_all_reference_crash_dumps,
    get_crash_dump_dir_paths,
    RefDump,
)

# A representative subset of commands to test in JSON mode.  We pick commands
# that exercise different output shapes: scalars, pointers, structs, arrays,
# multi-object pipelines, and error paths.
JSON_POS_CMDS = [
    # Single pointer
    "addr spa_namespace_avl",

    # Dereference
    "addr jiffies | deref",

    # Array values
    "spa | member spa_ubsync.ub_rootbp.blk_dva[0].dva_word",

    # Pipeline through member
    "spa | head 1 | member spa_name",

    # echo (void pointers)
    "echo 0x1 0x2 0x3",

    # count (single integer)
    "spa | count",

    # sum
    "echo 1 | echo 2 | sum",

    # empty pipeline
    "echo",

    # filter with no match
    "echo 0x0 | filter 'obj == 1'",

    # filter with match
    "echo 0x0 0x1 0x2 | filter 'obj == 1'",

    # sizeof
    "sizeof size_t",
    "sizeof task_struct",
]

# Commands that only work on the 201912060006 dump (different struct layouts)
JSON_POS_CMDS_201912060006 = [
    "addr spa_namespace_avl | member avl_root.avl_pcb avl_size",
]

JSON_NEG_CMDS = [
    # Unknown symbol
    "addr bogus",

    # Bogus member
    "spa | member spa_ubsync.bogus",

    # Bad filter expression (echo guarantees input so filter evaluates)
    "echo 0x1 | filter 'obj =='",
]

JSON_CMD_TABLE = JSON_POS_CMDS + JSON_NEG_CMDS
CMD_TABLE = JSON_CMD_TABLE


@pytest.mark.skipif(
    len(get_crash_dump_dir_paths()) == 0,
    reason="couldn't find any crash/core dumps to run tests against")
@pytest.mark.parametrize('rdump', get_all_reference_crash_dumps())
@pytest.mark.parametrize('cmd', JSON_POS_CMDS)
def test_json_positive_cmd(capsys: Any, rdump: RefDump, cmd: str) -> None:
    """
    Verify that successful commands produce valid JSON arrays where each
    entry has at least "type" and "value" keys.
    """
    exit_code = rdump.repl_invoke_json(cmd)
    captured = capsys.readouterr()

    assert exit_code == 0, f"Expected exit code 0, got {exit_code} for: {cmd}"

    result = json.loads(captured.out)
    assert isinstance(result, list), f"Expected JSON array, got: {type(result)}"

    for entry in result:
        assert isinstance(entry,
                          dict), f"Expected dict entry, got: {type(entry)}"
        assert "type" in entry, f"Missing 'type' key in JSON entry: {entry}"
        assert "value" in entry, f"Missing 'value' key in JSON entry: {entry}"


@pytest.mark.skipif(
    len(get_crash_dump_dir_paths()) == 0,
    reason="couldn't find any crash/core dumps to run tests against")
@pytest.mark.parametrize('rdump', get_all_reference_crash_dumps())
@pytest.mark.parametrize('cmd', JSON_POS_CMDS_201912060006)
def test_json_positive_cmd_201912060006(capsys: Any, rdump: RefDump,
                                        cmd: str) -> None:
    """
    Commands specific to the 201912060006 dump that may fail on other dumps
    due to different struct layouts.
    """
    if "201912060006" not in rdump.dump_name:
        pytest.skip("command only valid for dump.201912060006")

    exit_code = rdump.repl_invoke_json(cmd)
    captured = capsys.readouterr()

    assert exit_code == 0, f"Expected exit code 0, got {exit_code} for: {cmd}"
    result = json.loads(captured.out)
    assert isinstance(result, list)
    for entry in result:
        assert "type" in entry
        assert "value" in entry


@pytest.mark.skipif(
    len(get_crash_dump_dir_paths()) == 0,
    reason="couldn't find any crash/core dumps to run tests against")
@pytest.mark.parametrize('rdump', get_all_reference_crash_dumps())
@pytest.mark.parametrize('cmd', JSON_NEG_CMDS)
def test_json_negative_cmd(capsys: Any, rdump: RefDump, cmd: str) -> None:
    """
    Verify that error commands produce a JSON {"error": ...} response and a
    non-zero exit code.
    """
    exit_code = rdump.repl_invoke_json(cmd)
    captured = capsys.readouterr()

    assert exit_code != 0, f"Expected non-zero exit code for: {cmd}"

    result = json.loads(captured.out)
    assert isinstance(result,
                      dict), f"Expected JSON object, got: {type(result)}"
    assert "error" in result, f"Missing 'error' key in JSON response: {result}"


@pytest.mark.skipif(
    len(get_crash_dump_dir_paths()) == 0,
    reason="couldn't find any crash/core dumps to run tests against")
@pytest.mark.parametrize('rdump', get_all_reference_crash_dumps())
def test_json_pointer_value_is_integer(capsys: Any, rdump: RefDump) -> None:
    """
    Verify that pointer values (from addr) are serialized as integers.
    addr returns a pointer by value (not backed by memory), so there is
    no "address" field — only "type" and "value".
    """
    exit_code = rdump.repl_invoke_json("addr spa_namespace_avl")
    captured = capsys.readouterr()

    assert exit_code == 0
    result = json.loads(captured.out)
    assert len(result) == 1
    entry = result[0]
    assert "avl_tree_t" in entry["type"]
    assert isinstance(entry["value"], int)
    # By-value pointers have no backing address
    assert "address" not in entry


@pytest.mark.skipif(
    len(get_crash_dump_dir_paths()) == 0,
    reason="couldn't find any crash/core dumps to run tests against")
@pytest.mark.parametrize('rdump', get_all_reference_crash_dumps())
def test_json_address_has_hex(capsys: Any, rdump: RefDump) -> None:
    """
    Verify that objects backed by memory include an "address" field with
    a hex string.  We use 'addr jiffies | deref' which dereferences a
    kernel variable, producing an object with a backing memory address.
    """
    exit_code = rdump.repl_invoke_json("addr jiffies | deref")
    captured = capsys.readouterr()

    assert exit_code == 0
    result = json.loads(captured.out)
    assert len(result) >= 1
    entry = result[0]
    assert "address" in entry, f"Expected 'address' field: {entry}"
    assert entry["address"].startswith("0x"), \
        f"Expected hex address, got: {entry['address']}"


@pytest.mark.skipif(
    len(get_crash_dump_dir_paths()) == 0,
    reason="couldn't find any crash/core dumps to run tests against")
@pytest.mark.parametrize('rdump', get_all_reference_crash_dumps())
def test_json_count_returns_integer(capsys: Any, rdump: RefDump) -> None:
    """
    Verify that 'spa | count' returns a single entry with an integer value.
    """
    exit_code = rdump.repl_invoke_json("spa | count")
    captured = capsys.readouterr()

    assert exit_code == 0
    result = json.loads(captured.out)
    assert len(result) == 1
    assert isinstance(result[0]["value"], int), \
        f"Expected int value, got: {type(result[0]['value'])}"


@pytest.mark.skipif(
    len(get_crash_dump_dir_paths()) == 0,
    reason="couldn't find any crash/core dumps to run tests against")
@pytest.mark.parametrize('rdump', get_all_reference_crash_dumps())
def test_json_empty_pipeline(capsys: Any, rdump: RefDump) -> None:
    """
    Verify that an empty pipeline ('echo' with no args) returns an empty
    JSON array.
    """
    exit_code = rdump.repl_invoke_json("echo")
    captured = capsys.readouterr()

    assert exit_code == 0
    result = json.loads(captured.out)
    assert result == []


@pytest.mark.skipif(
    len(get_crash_dump_dir_paths()) == 0,
    reason="couldn't find any crash/core dumps to run tests against")
@pytest.mark.parametrize('rdump', get_all_reference_crash_dumps())
def test_json_spa_member_spa_name(capsys: Any, rdump: RefDump) -> None:
    """
    Verify the JSON representation of a char array (spa_name) — should be
    a string, not hex bytes.
    """
    exit_code = rdump.repl_invoke_json("spa | head 1 | member spa_name")
    captured = capsys.readouterr()

    assert exit_code == 0
    result = json.loads(captured.out)
    assert len(result) == 1

    entry = result[0]
    assert "char" in entry["type"], f"Expected char type, got: {entry['type']}"
    # The value should be a readable string, not hex
    assert isinstance(entry["value"], str), \
        f"Expected string value for char array, got: {type(entry['value'])}"


@pytest.mark.skipif(
    len(get_crash_dump_dir_paths()) == 0,
    reason="couldn't find any crash/core dumps to run tests against")
@pytest.mark.parametrize('rdump', get_all_reference_crash_dumps())
def test_json_stacks_has_structured_output(capsys: Any, rdump: RefDump) -> None:
    """
    Verify that 'stacks' as terminal command in JSON mode produces
    aggregated output with count, tasks list, and shared stack_trace.
    """
    exit_code = rdump.repl_invoke_json("stacks")
    captured = capsys.readouterr()

    assert exit_code == 0, f"Expected exit code 0, got {exit_code}"

    result = json.loads(captured.out)
    assert isinstance(result, list)
    assert len(result) > 0, "Expected at least one aggregated group"

    for entry in result:
        assert entry["type"] == "struct task_struct *"
        assert "state" in entry
        assert isinstance(entry["state"], str)
        assert "count" in entry
        assert isinstance(entry["count"], int)
        assert entry["count"] >= 1
        assert "tasks" in entry
        assert isinstance(entry["tasks"], list)
        assert len(entry["tasks"]) == entry["count"]
        for task in entry["tasks"]:
            assert "address" in task
            assert task["address"].startswith("0x")
            assert "comm" in task
            assert "pid" in task
        assert "stack_trace" in entry
        assert isinstance(entry["stack_trace"], list)
        for frame in entry["stack_trace"]:
            assert "function" in frame
            assert "offset" in frame


@pytest.mark.skipif(
    len(get_crash_dump_dir_paths()) == 0,
    reason="couldn't find any crash/core dumps to run tests against")
@pytest.mark.parametrize('rdump', get_all_reference_crash_dumps())
def test_json_stacks_roundtrip(capsys: Any, rdump: RefDump) -> None:
    """
    Verify that aggregated stacks JSON output is round-trip serializable.
    """
    exit_code = rdump.repl_invoke_json("stacks")
    captured = capsys.readouterr()

    assert exit_code == 0
    result = json.loads(captured.out)
    roundtripped = json.loads(json.dumps(result))
    assert result == roundtripped


@pytest.mark.skipif(
    len(get_crash_dump_dir_paths()) == 0,
    reason="couldn't find any crash/core dumps to run tests against")
@pytest.mark.parametrize('rdump', get_all_reference_crash_dumps())
def test_json_stacks_aggregated_output(capsys: Any, rdump: RefDump) -> None:
    """
    Verify that 'stacks' as the terminal command in JSON mode produces
    aggregated output with count, tasks list, and shared stack_trace.
    """
    exit_code = rdump.repl_invoke_json("stacks")
    captured = capsys.readouterr()

    assert exit_code == 0, f"Expected exit code 0, got {exit_code}"

    result = json.loads(captured.out)
    assert isinstance(result, list)
    assert len(result) > 0, "Expected at least one aggregated stack group"

    total_tasks = 0
    for entry in result:
        assert entry["type"] == "struct task_struct *"
        assert "state" in entry
        assert isinstance(entry["state"], str)
        assert "count" in entry
        assert isinstance(entry["count"], int)
        assert entry["count"] >= 1
        assert "tasks" in entry
        assert isinstance(entry["tasks"], list)
        assert len(entry["tasks"]) == entry["count"]
        for task in entry["tasks"]:
            assert "address" in task
            assert task["address"].startswith("0x")
            assert "comm" in task
            assert "pid" in task
        assert "stack_trace" in entry
        assert isinstance(entry["stack_trace"], list)
        total_tasks += entry["count"]

    # The number of groups should be <= total tasks (aggregation reduces)
    assert len(result) <= total_tasks


@pytest.mark.skipif(
    len(get_crash_dump_dir_paths()) == 0,
    reason="couldn't find any crash/core dumps to run tests against")
@pytest.mark.parametrize('rdump', get_all_reference_crash_dumps())
def test_json_stacks_aggregated_sorted_descending(capsys: Any,
                                                  rdump: RefDump) -> None:
    """
    Verify that aggregated stacks JSON output is sorted by count descending,
    matching the pretty-print behavior.
    """
    exit_code = rdump.repl_invoke_json("stacks")
    captured = capsys.readouterr()

    assert exit_code == 0
    result = json.loads(captured.out)
    counts = [entry["count"] for entry in result]
    assert counts == sorted(counts, reverse=True), \
        f"Expected counts sorted descending, got: {counts}"


@pytest.mark.skipif(
    len(get_crash_dump_dir_paths()) == 0,
    reason="couldn't find any crash/core dumps to run tests against")
@pytest.mark.parametrize('rdump', get_all_reference_crash_dumps())
def test_json_stacks_aggregated_with_filter(capsys: Any,
                                            rdump: RefDump) -> None:
    """
    Verify that 'stacks -m zfs' in JSON mode produces aggregated output
    filtered to ZFS module stacks only.
    """
    exit_code = rdump.repl_invoke_json("stacks -m zfs")
    captured = capsys.readouterr()

    assert exit_code == 0, f"Expected exit code 0, got {exit_code}"

    result = json.loads(captured.out)
    assert isinstance(result, list)
    # Should have at least one ZFS stack in the test dumps
    assert len(result) > 0, "Expected at least one ZFS stack group"

    for entry in result:
        assert "count" in entry
        assert "tasks" in entry
        assert "stack_trace" in entry


@pytest.mark.skipif(
    len(get_crash_dump_dir_paths()) == 0,
    reason="couldn't find any crash/core dumps to run tests against")
@pytest.mark.parametrize('rdump', get_all_reference_crash_dumps())
def test_json_stacks_aggregated_roundtrip(capsys: Any, rdump: RefDump) -> None:
    """
    Verify that aggregated stacks JSON output is round-trip serializable.
    """
    exit_code = rdump.repl_invoke_json("stacks")
    captured = capsys.readouterr()

    assert exit_code == 0
    result = json.loads(captured.out)
    roundtripped = json.loads(json.dumps(result))
    assert result == roundtripped


@pytest.mark.skipif(
    len(get_crash_dump_dir_paths()) == 0,
    reason="couldn't find any crash/core dumps to run tests against")
@pytest.mark.parametrize('rdump', get_all_reference_crash_dumps())
def test_json_roundtrip_serializable(capsys: Any, rdump: RefDump) -> None:
    """
    Verify that JSON output can be serialized and deserialized without
    data loss (round-trip test).
    """
    exit_code = rdump.repl_invoke_json(
        "spa | member spa_ubsync.ub_rootbp.blk_dva[0].dva_word")
    captured = capsys.readouterr()

    assert exit_code == 0
    result = json.loads(captured.out)

    # Round-trip: serialize and parse again
    roundtripped = json.loads(json.dumps(result))
    assert result == roundtripped
