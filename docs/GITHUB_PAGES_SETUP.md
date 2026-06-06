# GitHub Pages Setup Guide

The ChapterForge website is served via GitHub Pages from the `docs/` folder on the main branch.

## Current Configuration

- **Source**: `docs/` folder on `main` branch
- **Theme**: Minimal (via `_config.yml`)
- **Landing Page**: `landing.html`
- **Documentation Index**: `index.md`

## To Enable GitHub Pages

If GitHub Pages is not yet enabled:

1. Go to **Settings** → **Pages**
2. Under "Build and deployment":
   - **Source**: Select "Deploy from a branch"
   - **Branch**: Select `main` branch, `/docs` folder
3. Click **Save**

GitHub will automatically deploy after pushing changes to the main branch.

## Custom Domain (Optional)

To use a custom domain (e.g., `chapterforge.org`):

1. In **Settings** → **Pages**, under "Custom domain", enter your domain
2. Point your domain's DNS records to GitHub's servers:
   - Type A records to: `185.199.108.153`, `185.199.109.153`, `185.199.110.153`, `185.199.111.153`
   - Or Type AAAA records for IPv6 support
3. GitHub will automatically create a `CNAME` file

## Site Contents

The website includes:

- **landing.html** - Main landing/home page
- **html/USER_GUIDE.html** - User documentation
- **html/CHANGELOG.html** - Release history
- **html/THIRD_PARTY.html** - Open source licenses
- **html/LICENSE.txt** - MIT license text
- **README.md** - Quick reference

## Excluded from Public Site

The following files are excluded from the published website (see `_config.yml`):

- DEPLOYMENT.md - Build instructions (developers only)
- CODE_QUALITY.md - Quality guidelines (developers only)
- LINTING.md - Linting configuration (developers only)
- press-release-v1.0.0.md - Press release content

## Build and Deployment

The site is automatically built and deployed whenever:

1. You push changes to the `main` branch
2. GitHub Actions runs the Pages build workflow

No additional steps required - GitHub handles the build process.

## Troubleshooting

- **Site not updating**: Check that you pushed to the `main` branch
- **Deployment failed**: Check the "Actions" tab for build errors
- **Pages not enabled**: Go to Settings > Pages and verify configuration
- **Cache issues**: Try a hard refresh (Ctrl+Shift+R) to clear browser cache
