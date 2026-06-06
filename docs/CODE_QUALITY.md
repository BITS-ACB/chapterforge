# Code Quality Standards and Tools

ChapterForge uses a comprehensive set of quality assurance tools to maintain high code standards and catch issues early in the development process.

## Quality Assurance Tools

### 1. Ruff
**Purpose**: Fast Python linter and formatter
**Configuration**: `ruff.toml`
**Focus**: Code style, bugs, and complexity analysis

### 2. Black
**Purpose**: Code formatting
**Configuration**: `pyproject.toml`
**Focus**: Consistent code style

### 3. isort
**Purpose**: Import sorting
**Configuration**: `pyproject.toml`
**Focus**: Consistent import organization

### 4. mypy
**Purpose**: Static type checking
**Configuration**: `pyproject.toml`
**Focus**: Type safety and error detection

### 5. pylint
**Purpose**: Static code analysis
**Configuration**: `.pylintrc`
**Focus**: Code smells, potential bugs, and adherence to coding standards

### 6. flake8
**Purpose**: Style guide enforcement
**Configuration**: `.flake8`
**Focus**: PEP 8 compliance, complexity analysis

## Running Quality Checks

### Manual Execution

Run all quality checks at once:

```bash
# Install development dependencies
pip install -e .[dev]

# Run all quality checks
python scripts/run-quality-checks.py
```

### Individual Tool Execution

```bash
# Run Ruff linting and auto-fix issues
ruff check chapterforge/ --fix

# Run Black formatting
black chapterforge/

# Run isort import sorting
isort chapterforge/

# Run mypy type checking
mypy chapterforge/

# Run flake8 style checking
flake8 chapterforge/

# Run pylint analysis
pylint chapterforge/
```

## Pre-commit Hooks

To automatically run quality checks before each commit:

1. Install pre-commit:
   ```bash
   pip install pre-commit
   ```

2. Install the git hook scripts:
   ```bash
   pre-commit install
   ```

3. The hooks will now run automatically on every commit.

## Continuous Integration

All quality checks are automatically run in CI pipelines to ensure code meets standards before merging.

## Configuration Files

- `ruff.toml` - Ruff configuration
- `pyproject.toml` - Black, isort, mypy, and general project configuration
- `.pylintrc` - pylint configuration
- `.flake8` - flake8 configuration
- `.pre-commit-config.yaml` - pre-commit hooks configuration

## Benefits

This quality assurance setup helps prevent issues like:
- Code style inconsistencies
- Missing imports that could cause runtime errors
- Type-related errors
- Code smells and anti-patterns
- Unhandled exceptions
- Performance issues

## Code Standards

### Python Version
- Target: Python 3.8+
- Compatibility: Windows 10/11

### Code Style
- Follow PEP 8 guidelines
- Use descriptive variable and function names
- Keep functions focused and small
- Write docstrings for all public functions and classes
- Use type hints where appropriate

### Error Handling
- Handle exceptions gracefully
- Provide meaningful error messages
- Log errors appropriately
- Fail fast when encountering unrecoverable errors

### Testing
- Write unit tests for new functionality
- Maintain high test coverage
- Test edge cases and error conditions
- Use pytest for test framework

## Quality Gate Checklist

Before submitting a pull request, ensure:

- [ ] All quality checks pass
- [ ] Code follows established style guidelines
- [ ] New functionality is covered by tests
- [ ] Documentation is updated if needed
- [ ] Changes don't introduce new warnings or errors
- [ ] Performance impact is considered for critical paths

## Troubleshooting

### Common Issues

1. **Import errors in mypy**:
   ```bash
   # Add to mypy configuration if needed
   [tool.mypy]
   ignore_missing_imports = true
   ```

2. **Line length violations**:
   - Black handles most formatting
   - For long strings, consider breaking them up
   - For long function signatures, use multi-line parameters

3. **Pre-commit hook failures**:
   ```bash
   # Run pre-commit on all files to test
   pre-commit run --all-files
   ```

### Updating Tools

Keep quality assurance tools updated:

```bash
# Update all dev dependencies
pip install --upgrade -e .[dev]

# Update pre-commit hooks
pre-commit autoupdate
```