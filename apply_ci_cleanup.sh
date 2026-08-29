#!/usr/bin/env bash
set -euo pipefail
rm -f \
  templates/cash/close.html \
  templates/sales/pending.html \
  templates/sales/quotes.html \
  templates/sales/sales.html \
  templates/workspace/activity.html \
  templates/workspace/executive.html \
  templates/warehouse/transfers_by_warehouse.html

echo "Legacy duplicate templates removed."
echo "Now run: git add -A && git status"
