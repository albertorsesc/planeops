"""`plane init` wiring: the seed decision branches and the scaffold flow."""

import argparse
from pathlib import Path

import pytest

from planeops.cli import main
from planeops.cli.init import _should_seed


def _args(seed=False, no_seed=False):
    return argparse.Namespace(seed=seed, no_seed=no_seed)


def test_no_seed_flag_wins():
    assert _should_seed(_args(no_seed=True)) is False


def test_seed_flag_wins():
    assert _should_seed(_args(seed=True)) is True


def test_interactive_defaults_to_yes(monkeypatch):
    monkeypatch.setattr("builtins.input", lambda _p: "")
    assert _should_seed(_args()) is True  # bare Enter accepts the guided default


def test_interactive_n_declines(monkeypatch):
    monkeypatch.setattr("builtins.input", lambda _p: " N ")
    assert _should_seed(_args()) is False


def test_no_stdin_without_seed_flag_never_seeds(monkeypatch):
    def _eof(_p):
        raise EOFError

    monkeypatch.setattr("builtins.input", _eof)
    assert _should_seed(_args()) is False  # non-interactive: leave registry empty


def test_init_scaffolds_and_prints_next_steps(tmp_path, monkeypatch, capsys):
    # Route the config pointer into the sandbox so the developer's real
    # ~/.config/planeops is never touched.
    monkeypatch.setattr(
        "planeops.core.locate.config_home", lambda: tmp_path / "confighome"
    )
    inst = tmp_path / "inst"
    code = main(["init", str(inst), "--no-seed"])
    out = capsys.readouterr().out
    assert code == 0
    assert (inst / ".planeops").exists() and (inst / "registry").is_dir()
    assert "instance ready" in out
    assert "plane observe" in out  # the next step is always printed


@pytest.mark.parametrize("answer", ["y", "Y", "yes"])
def test_init_interactive_yes_triggers_the_seed(tmp_path, monkeypatch, answer):
    monkeypatch.setattr(
        "planeops.core.locate.config_home", lambda: tmp_path / "confighome"
    )
    monkeypatch.setattr("builtins.input", lambda _p: answer)
    seeded = []
    monkeypatch.setattr(
        "planeops.cli.init._seed_from_machine", lambda inst: seeded.append(inst)
    )
    assert main(["init", str(tmp_path / "inst")]) == 0
    assert seeded == [(tmp_path / "inst").resolve()]


# ---- location: asked, never guessed --------------------------------------


def _no_seed_env(monkeypatch, tmp_path):
    monkeypatch.setattr(
        "planeops.core.locate.config_home", lambda *a, **k: tmp_path / "cfg"
    )
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path / "home"))


def test_no_path_prompts_and_enter_accepts_the_default(tmp_path, monkeypatch):
    _no_seed_env(monkeypatch, tmp_path)
    prompts = []

    def fake_input(prompt):
        prompts.append(prompt)
        return ""

    monkeypatch.setattr("builtins.input", fake_input)
    assert main(["init", "--no-seed"]) == 0
    assert (tmp_path / "home" / "planeops" / ".planeops").exists()
    assert "create the instance at" in prompts[0]


def test_no_path_prompt_accepts_any_typed_path(tmp_path, monkeypatch):
    # Hidden directories and nested paths are first-class answers.
    _no_seed_env(monkeypatch, tmp_path)
    target = tmp_path / "home" / ".hidden" / "deep" / "inst"
    monkeypatch.setattr("builtins.input", lambda prompt: str(target))
    assert main(["init", "--no-seed"]) == 0
    assert (target / ".planeops").exists()


def test_no_path_without_stdin_refuses_to_guess(tmp_path, monkeypatch, capsys):
    _no_seed_env(monkeypatch, tmp_path)

    def no_stdin(prompt):
        raise EOFError

    monkeypatch.setattr("builtins.input", no_stdin)
    assert main(["init", "--no-seed"]) == 1
    assert not (tmp_path / "home" / "planeops").exists()
    err = capsys.readouterr().err
    assert "--yes" in err and "path" in err


def test_no_path_with_yes_takes_the_default_without_asking(tmp_path, monkeypatch):
    _no_seed_env(monkeypatch, tmp_path)

    def boom(prompt):
        raise AssertionError("must not prompt with --yes")

    monkeypatch.setattr("builtins.input", boom)
    assert main(["init", "--no-seed", "--yes"]) == 0
    assert (tmp_path / "home" / "planeops" / ".planeops").exists()


def test_explicit_hidden_nested_path_works(tmp_path, monkeypatch):
    _no_seed_env(monkeypatch, tmp_path)
    target = tmp_path / "home" / ".config" / "custom" / "spot"
    assert main(["init", str(target), "--no-seed"]) == 0
    assert (target / ".planeops").exists()
