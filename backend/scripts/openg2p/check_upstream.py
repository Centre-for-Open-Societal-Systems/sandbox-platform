"""Watch OpenG2P Partner Management and the COSS Consent Manager for changes that may
change the sandbox's contract (app/integrations/openg2p_contract.py).

For every watched (repository, branch) it reports:

* commits after the pinned ref that touch the contract files (schemas, controllers,
  models, config) - read them, they may need a sandbox change;
* release branches / tags the contract has no profile for (e.g. a new PM 1.1);
* drift of what the sandbox relies on, read from the branch head:
  - PM ``PolicyInput`` / ``OnboardingRequestCreate`` fields, CM ``PolicyUpsert`` fields:
    a field the sandbox sends that is gone = BREAKING; a new upstream field = NEW;
  - staff API routes the sandbox calls that are gone = BREAKING.

Exit 0: nothing changed since the pinned refs. Exit 1: something to look at (the
report says what). Exit 2: the check itself failed (network, git).

    python backend/scripts/openg2p/check_upstream.py                 # report to stdout
    python backend/scripts/openg2p/check_upstream.py --report out.md # also write markdown
    python backend/scripts/openg2p/check_upstream.py --cache .og2p   # reuse clones

Needs only git and Python 3.11+ (no project dependencies), so CI can run it as is
(.github/workflows/openg2p-upstream.yml, weekly). Upgrading after a report:
docs/OPENG2P_INTEGRATION.md.
"""

from __future__ import annotations

import argparse
import ast
import importlib.util
import re
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve()
CONTRACT_FILE = HERE.parents[2] / "app" / "integrations" / "openg2p_contract.py"


def load_contract():
    spec = importlib.util.spec_from_file_location("openg2p_contract", CONTRACT_FILE)
    module = importlib.util.module_from_spec(spec)
    sys.modules["openg2p_contract"] = module  # dataclasses resolve their module by name
    spec.loader.exec_module(module)
    return module


def git(cwd: Path, *args: str) -> str:
    return subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True, text=True).stdout


def checkout(cache: Path, repo: str) -> Path:
    """A blobless clone of ``repo`` under ``cache`` (fetched again when it exists)."""
    path = cache / re.sub(r"[^A-Za-z0-9]+", "_", repo)
    if not (path / ".git").exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        subprocess.run(["git", "clone", "--quiet", "--filter=blob:none", "--no-checkout", repo, str(path)],
                       check=True, capture_output=True, text=True)
    git(path, "fetch", "--quiet", "--tags", "--prune", "origin")
    return path


def show(path: Path, ref: str, file: str) -> str | None:
    try:
        # cat-file, not show: "show <ref>:<path>" may be read as a file name (Windows long paths).
        return git(path, "cat-file", "-p", f"{ref}:{file}")
    except subprocess.CalledProcessError:
        return None


def class_fields(source: str | None, name: str) -> list[str] | None:
    """Annotated field names of a pydantic class (and its in-file bases)."""
    if source is None:
        return None
    tree = ast.parse(source)
    classes = {n.name: n for n in tree.body if isinstance(n, ast.ClassDef)}

    def fields(cls: ast.ClassDef) -> list[str]:
        out: list[str] = []
        for base in cls.bases:
            if isinstance(base, ast.Name) and base.id in classes:
                out += [f for f in fields(classes[base.id]) if f not in out]
        for node in cls.body:
            if (isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name)
                    and node.target.id != "model_config" and node.target.id not in out):
                out.append(node.target.id)
        return out

    return fields(classes[name]) if name in classes else None


def routes(path: Path, ref: str, controller_dir: str) -> set[str]:
    """Paths registered with add_api_route, with the router's prefix."""
    try:
        files = git(path, "ls-tree", "-r", "--name-only", ref, controller_dir).split()
    except subprocess.CalledProcessError:
        return set()
    found: set[str] = set()
    for file in files:
        source = show(path, ref, file) or ""
        prefix = "".join(re.findall(r'router\.prefix\s*\+=\s*"([^"]*)"', source))
        for route in re.findall(r'add_api_route\(\s*"([^"]*)"', source):
            found.add(prefix + route)
    return found


def compare(title: str, sent: tuple[str, ...], upstream: list[str] | None, lines: list[str]) -> bool:
    if upstream is None:
        lines.append(f"- **BREAKING** {title}: not found upstream (renamed or moved?)")
        return True
    gone = [f for f in sent if f not in upstream]
    new = [f for f in upstream if f not in sent]
    for f in gone:
        lines.append(f"- **BREAKING** {title}: `{f}` (sent by the sandbox) is gone")
    for f in new:
        lines.append(f"- NEW {title}: `{f}`")
    return bool(gone or new)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--cache", type=Path, default=None, help="Keep the clones here (default: a temp dir)")
    parser.add_argument("--report", type=Path, default=None, help="Also write the markdown report here")
    args = parser.parse_args()
    c = load_contract()
    tmp = None
    cache = args.cache
    if cache is None:
        tmp = tempfile.TemporaryDirectory()
        cache = Path(tmp.name)

    lines = ["# OpenG2P upstream check", ""]
    changed = False
    try:
        clones = {}
        for repo, branch, pinned, paths in c.WATCHED:
            path = clones.get(repo) or checkout(cache, repo)
            clones[repo] = path
            head = git(path, "rev-parse", "--short", f"origin/{branch}").strip()
            commits = git(path, "log", "--format=%h %ad %s", "--date=short",
                          f"{pinned}..origin/{branch}", "--", *paths).strip().splitlines()
            lines.append(f"## {repo.rsplit('/', 1)[-1]} `{branch}` (pinned {pinned}, head {head})")
            if commits:
                changed = True
                lines.append(f"{len(commits)} commit(s) touching the contract files since {pinned}:")
                lines += [f"- {line}" for line in commits]
            else:
                lines.append("No contract-relevant commits since the pinned ref.")
            lines.append("")

        # Drift at the branch heads.
        lines.append("## Drift (branch heads vs openg2p_contract.py)")
        pm_path = clones[c.PM_REPO]
        api = "core/api/src/openg2p_partner_management_api"
        drift = False
        for name, profile in c.PM_PROFILES.items():
            ref = f"origin/{profile.branch}"
            onboarding = class_fields(show(pm_path, ref, f"{api}/schemas/request.py"), "OnboardingRequestCreate")
            drift |= compare(f"PM {name} OnboardingRequestCreate", c.PM_ONBOARDING_FIELDS[name], onboarding, lines)
            if profile.policies:
                policy = class_fields(show(pm_path, ref, f"{api}/schemas/policy.py"), "PolicyInput")
                drift |= compare(f"PM {name} PolicyInput", c.PM_POLICY_FIELDS, policy, lines)
            have = routes(pm_path, ref, f"{api}/controllers")
            for route in c.PM_ROUTES[name]:
                if route not in have:
                    drift = True
                    lines.append(f"- **BREAKING** PM {name} route `{route}` is gone")
        cm_path = clones[c.CM_REPO]
        cm_api = "backend/src/openg2p_consent_manager"
        upsert = class_fields(show(cm_path, f"origin/{c.CM_BRANCH}", f"{cm_api}/schemas/partner.py"), "PolicyUpsert")
        drift |= compare("CM PolicyUpsert", c.CM_POLICY_FIELDS, upsert, lines)
        have = routes(cm_path, f"origin/{c.CM_BRANCH}", f"{cm_api}/controllers")
        for route in c.CM_ROUTES:
            if route not in have:
                drift = True
                lines.append(f"- **BREAKING** CM route `{route}` is gone")
        if not drift:
            lines.append("None.")
        changed |= drift
        lines.append("")

        # Releases without a profile.
        known = {p.branch for p in c.PM_PROFILES.values()}
        heads = git(pm_path, "branch", "-r", "--format=%(refname:short)").split()
        releases = sorted({h.removeprefix("origin/") for h in heads
                           if re.fullmatch(r"origin/\d+\.\d+(\.\d+)?", h)} - known)
        tags = sorted(t for t in git(pm_path, "tag", "--list").split() if re.match(r"v?\d+\.\d+", t))
        lines.append("## PM releases")
        lines.append(f"Profiles: {', '.join(sorted(c.PM_PROFILES))}. Release tags: {', '.join(tags) or 'none'}.")
        if releases:
            changed = True
            lines.append("**New release branch(es) without a profile:** " + ", ".join(releases))
    except (subprocess.CalledProcessError, OSError) as exc:
        detail = getattr(exc, "stderr", "") or str(exc)
        print(f"check failed: {detail}", file=sys.stderr)
        return 2
    finally:
        if tmp is not None:
            tmp.cleanup()

    lines += ["", "Result: " + ("**changes to review** (docs/OPENG2P_INTEGRATION.md)" if changed else "up to date")]
    report = "\n".join(lines) + "\n"
    print(report)
    if args.report:
        args.report.write_text(report, encoding="utf-8")
    return 1 if changed else 0


if __name__ == "__main__":
    sys.exit(main())
