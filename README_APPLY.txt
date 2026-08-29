Extract this ZIP into the repository root, overwriting files, then run:

  bash apply_ci_cleanup.sh
  git add -A
  git status
  git commit -m "FIX CI PostgreSQL and POS contracts"
  git push origin Orbiserp

The cleanup script removes legacy templates that must not remain in an existing working tree.
