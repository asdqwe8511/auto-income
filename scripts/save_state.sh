#!/usr/bin/env bash
# 큐/상태 파일을 저장소에 다시 커밋한다. (DB 대신 깃을 쓰기 때문)
set -uo pipefail

git config user.name  "auto-income-bot"
git config user.email "auto-income-bot@users.noreply.github.com"

git add data
if git diff --cached --quiet; then
  echo "변경 없음 - 커밋 생략"
  exit 0
fi

git commit -m "chore(data): ${1:-update} [skip ci]"

BRANCH="${GITHUB_REF_NAME:-main}"
for i in 1 2 3 4 5; do
  if git push origin "HEAD:${BRANCH}"; then
    echo "저장 완료"
    exit 0
  fi
  echo "푸시 충돌 - 다시 시도 ($i/5)"
  git pull --rebase -X theirs origin "${BRANCH}" || git rebase --abort || true
  sleep 4
done

echo "저장 실패"
exit 1
