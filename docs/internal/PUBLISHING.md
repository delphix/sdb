# Publishing SDB to PyPI

This document describes how to set up and publish SDB to PyPI.

## Automated Publishing (Recommended)

SDB uses GitHub Actions with **Trusted Publishing** (OIDC) for secure, automated releases. This is the recommended method as it doesn't require storing API tokens.

### One-Time Setup

1. **Create a PyPI Account**
   - Go to [https://pypi.org/account/register/](https://pypi.org/account/register/)
   - Verify your email address

2. **Register the Project Name**
   - The first time you publish, PyPI will automatically register the project name `sdb`
   - Alternatively, you can manually publish once using the manual script to reserve the name

3. **Configure Trusted Publishing**
   
   This allows GitHub Actions to publish without API tokens:
   
   - Go to [https://pypi.org/manage/account/publishing/](https://pypi.org/manage/account/publishing/)
   - Click "Add a new pending publisher" (or "Add a new publisher" if the project exists)
   - Fill in the details:
     - **PyPI Project Name**: `sdb-debugger`
     - **Owner**: `sdimitro`
     - **Repository name**: `sdb`
     - **Workflow name**: `release.yml`
     - **Environment name**: `pypi`
   - Click "Add"

4. **Create GitHub Environment**
   
   - Go to your GitHub repository → Settings → Environments
   - Click "New environment"
   - Name it `pypi`
   - Optionally add protection rules (e.g., required reviewers)

### Creating a Release

Once the one-time setup is complete, releasing is simple:

```bash
# Create and push a version tag
git tag v0.2.0
git push origin v0.2.0
```

This will:
1. Trigger the release workflow
2. Run all CI checks (lint, type-check, unit tests, integration tests)
3. Build the package (source distribution + wheel)
4. Publish to PyPI
5. Create a GitHub Release with auto-generated release notes

### Version Format

- Use semantic versioning: `vMAJOR.MINOR.PATCH` (e.g., `v0.2.0`, `v1.0.0`)
- The `v` prefix is required for the workflow to trigger
- The version in the package is automatically derived from the git tag

## Manual Publishing

For manual publishing (e.g., testing, hotfixes), use the provided script:

### Prerequisites

```bash
pip install build twine
```

### Publishing to TestPyPI (Recommended for Testing)

Always test on TestPyPI first:

```bash
./scripts/publish-to-pypi.sh test
```

Install from TestPyPI to verify:
```bash
pip install --index-url https://test.pypi.org/simple/ sdb-debugger
```

### Publishing to PyPI

```bash
./scripts/publish-to-pypi.sh
```

### Authentication for Manual Publishing

The script supports two authentication methods:

1. **API Token (Recommended)**
   
   Create an API token at [https://pypi.org/manage/account/token/](https://pypi.org/manage/account/token/)
   
   Then either:
   ```bash
   # Set environment variables
   export TWINE_USERNAME=__token__
   export TWINE_PASSWORD=pypi-your-token-here
   ./scripts/publish-to-pypi.sh
   ```
   
   Or create `~/.pypirc`:
   ```ini
   [pypi]
   username = __token__
   password = pypi-your-token-here
   
   [testpypi]
   username = __token__
   password = pypi-your-testpypi-token-here
   ```

2. **Interactive Login**
   
   If no credentials are configured, twine will prompt for username and password.

## Troubleshooting

### "Project name already exists"

The name `sdb-debugger` may already be taken on PyPI. Check [https://pypi.org/project/sdb-debugger/](https://pypi.org/project/sdb-debugger/).

### Trusted Publishing Not Working

- Ensure the GitHub environment is named exactly `pypi`
- Verify the workflow file is named `release.yml`
- Check that the repository and owner match exactly in PyPI settings
- Make sure the tag starts with `v` (e.g., `v0.2.0`)

### Version Already Exists

PyPI doesn't allow overwriting existing versions. You must increment the version number for each release.

### Build Fails

Ensure you have a clean git state with the version tag:
```bash
git status  # Should be clean
git describe --tags  # Should show the version tag
```

## Testing the Package Locally

Before publishing, you can test the package locally:

```bash
# Build the package
pip install build
python -m build

# Install the built package
pip install dist/sdb_debugger-*.whl

# Test it works
sdb --help
python -c "import sdb; print(sdb.__version__)"
```
