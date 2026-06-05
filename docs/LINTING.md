# Code Quality and Linting

ChapterForge uses a comprehensive set of linting tools to ensure code quality and catch potential issues early in the development process.

## Linting Tools

The following tools are used for code quality checks:

### 1. pylint
- **Purpose**: Static code analysis for Python
- **Configuration**: `.pylintrc`
- **Focus**: Code smells, potential bugs, and adherence to coding standards

### 2. flake8
- **Purpose**: Style guide enforcement
- **Configuration**: `.flake8`
- **Focus**: PEP 8 compliance, complexity analysis

### 3. mypy
- **Purpose**: Static type checking
- **Configuration**: `.mypy.ini`
- **Focus**: Type safety and error detection

### 4. black
- **Purpose**: Code formatting
- **Focus**: Consistent code style

### 5. isort
- **Purpose**: Import sorting
- **Focus**: Consistent import organization

## Running Linting Tools

### Manual Execution

Run all linting checks at once:

**Windows:**
```cmd
lint.bat
```

**Linux/macOS:**
```bash
./lint.sh
```

### Individual Tool Execution

```bash
# Run flake8
flake8 chapterforge/ tests/

# Run pylint
pylint chapterforge/

# Run mypy
mypy chapterforge/

# Run black (formatting)
black chapterforge/ tests/

# Run isort (import sorting)
isort chapterforge/ tests/
```

## Pre-commit Hooks

To automatically run linting checks before each commit:

1. Install pre-commit:
   ```bash
   pip install pre-commit
   ```

2. Install the git hook scripts:
   ```bash
   pre-commit install
   ```

3. The hooks will now run automatically on every commit.

## Development Dependencies

Install all development dependencies including linting tools:

```bash
pip install -e .[dev]
```

## Configuration Files

- `.pylintrc` - pylint configuration
- `.flake8` - flake8 configuration
- `.mypy.ini` - mypy configuration
- `.pre-commit-config.yaml` - pre-commit hooks configuration

## Benefits

This linting setup helps prevent issues like:
- Missing imports that could cause freezing
- Unhandled exceptions
- Code smells and anti-patterns
- Inconsistent code style
- Type-related errors

## Continuous Integration

Linting checks are automatically run in CI pipelines to ensure all code meets quality standards before merging.