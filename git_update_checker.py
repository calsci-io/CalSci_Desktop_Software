import git

def repo_status(repo_path, branch="main"):
    repo = git.Repo(repo_path)
    repo.remotes.origin.fetch()

    local = repo.commit(branch)
    remote = repo.commit(f"origin/{branch}")

    behind = sum(1 for _ in repo.iter_commits(f"{branch}..origin/{branch}"))
    ahead  = sum(1 for _ in repo.iter_commits(f"origin/{branch}..{branch}"))

    return ahead, behind


ahead, behind = repo_status("./calsci_latest_itr_python")

if behind > 0:
    print(f"Update available ({behind} commits)")
elif ahead > 0:
    print(f"Local repo ahead by {ahead} commits")
else:
    print("Repo in sync")
