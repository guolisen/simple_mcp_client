
1523  gh auth login
1525  git status
1526  git add .
1527  git commit -m "fix release workflow"
1528  git push
1529  git tag v1.0.3
1530  git push origin v1.0.3
1531  gh release create v1.0.3
