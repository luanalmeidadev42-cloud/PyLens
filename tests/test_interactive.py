from pylens.interface import interactive


def test_guided_menu_builds_run_command_for_shared_cli(monkeypatch, capsys):
    answers = iter(
        [
            "1",
            "/tmp/demo.py",
            "deep",
            "",
            "",
            "150",
            "",
            "",
            "--seconds 2",
            "0",
        ]
    )
    calls = []
    monkeypatch.setattr("builtins.input", lambda prompt: next(answers))
    monkeypatch.setattr(
        interactive,
        "command_line_main",
        lambda arguments: calls.append(arguments) or 0,
    )

    assert interactive.main() == 0
    capsys.readouterr()

    assert calls == [
        [
            "run",
            "/tmp/demo.py",
            "--mode",
            "deep",
            "--timeout",
            "120",
            "--memory-limit-mib",
            "2048",
            "--cpu-limit-percent",
            "150.0",
            "--",
            "--seconds",
            "2",
        ]
    ]
