# Publishing this repo

> Published 2026-06-27 to https://github.com/CaskeyCoding/ballast (public), from the clean-history
> `public` branch. **Never `git push origin master`** from this local repo: `master` contains
> private working history. Only the rebuilt public snapshot is ever pushed. To update the public
> repo, rebuild the `public` branch from `master` (recipe in step 3) and push `public:main`.
> A `pre-push` hook enforces this: it rejects any push that is not `public` -> `main`. The hook
> is versioned in `.githooks/`; activate it once per clone with
> `git config core.hooksPath .githooks`.

Checklist before publishing an update.

1. **Gate is green.** `python scripts/local_ci.py` passes, including the `leak scan` step (a
   forbidden pattern in any tracked file fails the build) and the `secret scan`.
2. **Internal planning docs stay out.** The `proposals/` directory is git-ignored on purpose. It
   holds internal planning notes that must never ship in the public repo. Keep them local; do not
   re-add them. `.leak_scan_terms` (local leak-scan config) is likewise git-ignored and stays
   local.
3. **Publish from a clean history (important).** `master` is private working history and stays
   local. The public repo is a single orphan snapshot commit of the current tree. Activate the
   versioned pre-push hook once per clone (it enforces the `public` -> `main`-only rule, the
   single-commit snapshot, the leak scan, and the noreply identity):

   ```
   git config core.hooksPath .githooks
   ```

   To publish, rebuild the `public` branch and push only that branch:

   ```
   git checkout master
   git branch -D public
   git checkout --orphan public && git add -A && git commit -m "Ballast: initial public release"
   git checkout master
   git push --force-with-lease origin public:main
   ```

   Use the repo owner's GitHub noreply identity for the snapshot commit (set `GIT_AUTHOR_NAME`,
   `GIT_AUTHOR_EMAIL`, `GIT_COMMITTER_NAME`, `GIT_COMMITTER_EMAIL` to
   `CaskeyCoding` / `10975324+CaskeyCoding@users.noreply.github.com` for the commit), so no
   personal email address ships in public commit metadata.

   The `leak scan` gate checks the working tree, not historical commits, which is why the
   single-commit snapshot branch matters. `--force-with-lease` is required because each rebuild
   rewrites the snapshot history.
4. **Pick a repository license.** Add a top-level LICENSE. The corpus documents carry their own
   per-file provenance and license frontmatter (federal public-domain sources, plus the author's
   own methodology notes); the repository license covers the code.
5. **Final disclosure pass.** Run the disclosure-auditor over the whole tree once more as the
   publish-time gate, and run `scripts/secret_scan.py` and `scripts/leak_scan.py` against the
   snapshot checkout.
