#!/bin/bash
git init
git add .
git commit -m "initial commit: iamconvert bot"
git branch -M main
git remote add origin https://github.com/theRishu/iamconvert.git
git push -u origin main
