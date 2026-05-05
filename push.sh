#!/bin/bash
git init
git add .
git commit -m "Final fixed version: IamConvert Bot"
git branch -M main
git remote set-url origin https://github.com/theRishu/iamconvert.git || git remote add origin https://github.com/theRishu/iamconvert.git
git push -u origin main -f
