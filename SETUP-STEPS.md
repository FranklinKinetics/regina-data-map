# Setup steps (for Brandon; delete this file after setup)

Everything is already built and tested on your computer. These are the clicks only you can do.

1. **Make a free GitHub account** at github.com (skip if you have one). Choose a username you are happy to see in the web address, because it becomes `https://USERNAME.github.io/regina-data-map/`.
2. **Create an empty repository** (the green "New" button).
   - Name: `regina-data-map`
   - Public
   - Do NOT tick "Add a README", ".gitignore" or a licence (it must start empty).
3. **Tell Claude your username.** Claude will check what is about to be uploaded with you and, when you say go, upload it. A GitHub sign-in window will pop up on your screen once; sign in there. (Claude never sees your password.)
4. **Turn on Pages.** In the repo: Settings > Pages > Source: choose **GitHub Actions**.
5. **Run the first refresh.** Actions tab > Refresh Regina Data Map > Run workflow. It takes a few minutes. Green tick = published.
6. **Tell Claude the first run finished** (or send the red error text if it failed). Claude then rebuilds the store zip with your address inside, and you upload that zip to the Squarespace product.

After that it runs by itself every Friday. GitHub emails you if a run fails; the last good data stays live.
