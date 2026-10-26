# HW7 Part 6: File tools and Bash safety gate

`SandboxFileTools` implements the six required tools: `read_file(max_lines)`,
`write_file`, `edit_file` (bounded unified diff), `glob_files`,
`search_in_files(file_pattern)`, and `bash`. Every filesystem path is resolved
against one existing temporary sandbox root. Absolute paths, `..` traversal,
and symlinks resolving outside that root are rejected.

The module-level `SAFE_PREFIXES` contains `pwd`, `ls`, `find`, `grep`, and
`wc`. `confirm_bash(command, auto_approve=False)` auto-approves only one of
these prefixes when the separate destructive check passes. Other
non-destructive commands require explicit confirmation. Commands run with
`shell=False`, a ten-second timeout, bounded output, and the sandbox as `cwd`.

`is_destructive(command)` is evaluated before either manual or automatic
approval. It blocks recursive deletion, privilege escalation,
permission/ownership changes, filesystem-formatting commands, raw device
writes, and redirection/`tee` to root paths. Destructive commands therefore
remain blocked even when `approved=True`.

## Integration and safety results

The integration fixture creates `alpha.py`, `beta.py`, and `gamma.py` in a
temporary directory. The required sequence is recorded as
`glob_files("*.py")` -> `search_in_files("DEBUG", "*.py")` ->
`read_file("beta.py")`; it finds and displays `DEBUG = True`.

The combined safety test passes five benign commands and blocks five dangerous
commands. The committed raw result records 10/10 PASS without saving the
temporary absolute path or executing any destructive command.

```zsh
.venv/bin/python code/test_hw7_part6_file_tools.py
.venv/bin/python code/hw7_part6_file_tools.py --write-evidence
```

Use the second command for the single Part 6 report screenshot. The evidence
file is `reports/hw07/raw/part6_safety_results.json`.
