# feedback-hub Production Checklist

## Help Menu Item

The menu item is **Help > Report an Issue...**
Keyboard shortcut: **Alt+H** to open Help menu, then **R**

---

## Is It Working Right Now?

**Short answer: Not yet for end users.**

The dialog opens fine, but submissions will silently fail because the
GitHub token is currently empty in the running app. Here is the exact
state of each path:

| Path | Status | Why |
|------|--------|-----|
| Running from source (`python main.py`) | Broken | Token env var not set |
| Installed binary (current v2.0.0 installer) | Broken | Binary was built before this change |
| Next release binary (built via CI) | Working | Build workflow injects the token |
| Dev machine with env var set | Working | Set `CHAPTERFORGE_GITHUB_TOKEN` |

---

## What You Must Do to Ship This

### Step 1 - Create a proper fine-grained token (5 minutes)

The token currently stored in GitHub Secrets is a broad OAuth token.
Replace it with a minimal fine-grained PAT that can only write issues.

1. Open: https://github.com/settings/personal-access-tokens/new
2. Fill in:
   - **Name**: `chapterforge-feedback-hub`
   - **Expiration**: 1 year
   - **Repository access**: Only select repositories -> `BITS-ACB/chapterforge`
   - **Permissions**: Issues = Read and Write (everything else = No access)
3. Click **Generate token** and copy it
4. Store it as the repo secret (run this in the terminal):

```
! echo "github_pat_YOUR_NEW_TOKEN_HERE" | gh secret set CHAPTERFORGE_GITHUB_TOKEN --repo BITS-ACB/chapterforge
```

### Step 2 - Install feedback-hub as a proper dependency (2 minutes)

Add to `requirements.txt`:

```
feedback-hub>=1.0
```

Then verify locally:
```
pip install feedback-hub
python -c "import feedback_hub; print(feedback_hub.__version__)"
```

### Step 3 - Rebuild and release (10 minutes)

The build workflow (`build-release.yml`) automatically injects the token
at build time. To trigger it:

**Option A - Trigger the release workflow manually:**
```
gh workflow run build-release.yml --repo BITS-ACB/chapterforge
```

**Option B - Create a new release (recommended):**
Update the version, tag, and release as normal. The workflow fires on
`release: published` and uploads the installer with the token baked in.

### Step 4 - Verify it works

After the installer is built and installed:
1. Open ChapterForge
2. Press **Alt+H** to open Help menu
3. Press **R** for Report an Issue
4. Fill in the form and submit
5. Check https://github.com/BITS-ACB/chapterforge/issues - your issue should appear

---

## For Local Development / Testing Right Now

To test the dialog immediately from source without waiting for a release:

```powershell
# In PowerShell before running main.py:
$env:CHAPTERFORGE_GITHUB_TOKEN = "your-token-here"
python main.py
```

Or add it to a `.env` file (never commit this):
```
CHAPTERFORGE_GITHUB_TOKEN=your-token-here
```

---

## Token Rotation

The fine-grained PAT expires in 1 year. When it does:
1. Create a new one at https://github.com/settings/personal-access-tokens
2. Same settings: `BITS-ACB/chapterforge`, Issues read/write only
3. Run: `! echo "github_pat_NEW_TOKEN" | gh secret set CHAPTERFORGE_GITHUB_TOKEN --repo BITS-ACB/chapterforge`
4. Trigger a new release build to bake it in

---

## feedback-hub Library

Source: https://github.com/Community-Access/feedback-hub

To integrate with other apps (GLOW, QUILL):
- See `C:\code\feedback-hub\INTEGRATING.md`
- GLOW: one-line change in `routes/feedback.py`
- QUILL: replace `report_bug()` in `main_frame.py`
