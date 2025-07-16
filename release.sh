#!/bin/bash

# GitHub Release Script with Verification
# Usage: ./release.sh <version>
# Example: ./release.sh 1.0.4

set -e  # Exit on any error

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Function to print colored output
print_status() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

print_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Function to check if command exists
command_exists() {
    command -v "$1" >/dev/null 2>&1
}

# Function to wait for user confirmation
confirm() {
    read -p "$(echo -e "${YELLOW}$1 (y/N):${NC} ")" -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        print_error "Operation cancelled by user"
        exit 1
    fi
}

# Function to check git status
check_git_status() {
    if [[ -n $(git status --porcelain) ]]; then
        print_error "Working directory is not clean. Please commit or stash changes first."
        git status --short
        exit 1
    fi
    print_success "Working directory is clean"
}

# Function to validate version format
validate_version() {
    if [[ ! $1 =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]]; then
        print_error "Invalid version format. Expected: X.Y.Z (e.g., 1.0.4)"
        exit 1
    fi
    print_success "Version format is valid: $1"
}

# Function to check if version already exists
check_version_exists() {
    if git tag | grep -q "^v$1$"; then
        print_error "Version v$1 already exists as a git tag"
        exit 1
    fi
    print_success "Version v$1 is available"
}

# Function to update version in files
update_version() {
    local version=$1
    
    print_status "Updating version to $version in setup.py..."
    sed -i.bak "s/version=\"[0-9]*\.[0-9]*\.[0-9]*\"/version=\"$version\"/" setup.py
    
    print_status "Updating version to $version in pyproject.toml..."
    sed -i.bak "s/version = \"[0-9]*\.[0-9]*\.[0-9]*\"/version = \"$version\"/" pyproject.toml
    
    # Remove backup files
    rm -f setup.py.bak pyproject.toml.bak
    
    print_success "Version updated in both files"
}

# Function to verify version consistency
verify_version_consistency() {
    local version=$1
    
    local setup_version=$(grep -o 'version="[0-9]*\.[0-9]*\.[0-9]*"' setup.py | grep -o '[0-9]*\.[0-9]*\.[0-9]*')
    local pyproject_version=$(grep -o 'version = "[0-9]*\.[0-9]*\.[0-9]*"' pyproject.toml | grep -o '[0-9]*\.[0-9]*\.[0-9]*')
    
    if [[ "$setup_version" != "$version" ]]; then
        print_error "setup.py version ($setup_version) doesn't match expected version ($version)"
        exit 1
    fi
    
    if [[ "$pyproject_version" != "$version" ]]; then
        print_error "pyproject.toml version ($pyproject_version) doesn't match expected version ($version)"
        exit 1
    fi
    
    print_success "Version consistency verified: $version"
}

# Function to run tests
run_tests() {
    print_status "Running tests..."
    if command_exists pytest; then
        pytest tests -v --cov=apple_search_ads --cov-report=term-missing
        print_success "Tests passed"
    else
        print_warning "pytest not found, skipping tests"
        confirm "Continue without running tests?"
    fi
}

# Function to run linting
run_linting() {
    print_status "Running code quality checks..."
    
    if command_exists black; then
        print_status "Running black formatter check..."
        black --check src tests
        print_success "Code formatting is correct"
    else
        print_warning "black not found, skipping formatting check"
    fi
    
    if command_exists mypy; then
        print_status "Running mypy type checking..."
        mypy src
        print_success "Type checking passed"
    else
        print_warning "mypy not found, skipping type checking"
    fi
    
    if command_exists flake8; then
        print_status "Running flake8 linting..."
        flake8 src tests --count --max-complexity=10 --max-line-length=127 --statistics
        print_success "Linting passed"
    else
        print_warning "flake8 not found, skipping linting"
    fi
}

# Function to create and push commit
create_commit() {
    local version=$1
    
    print_status "Creating commit for version $version..."
    git add setup.py pyproject.toml
    git commit -m "Bump version to $version for release

🤖 Generated with [Claude Code](https://claude.ai/code)

Co-Authored-By: Claude <noreply@anthropic.com>"
    
    print_success "Commit created"
}

# Function to create and push tag
create_tag() {
    local version=$1
    
    print_status "Creating and pushing tag v$version..."
    git tag -a "v$version" -m "Release version $version

🤖 Generated with [Claude Code](https://claude.ai/code)

Co-Authored-By: Claude <noreply@anthropic.com>"
    
    git push origin main
    git push origin "v$version"
    
    print_success "Tag v$version created and pushed"
}

# Function to wait for GitHub Actions
wait_for_actions() {
    local version=$1
    
    print_status "Waiting for GitHub Actions to complete..."
    sleep 10  # Give GitHub a moment to register the push
    
    local max_attempts=30
    local attempt=0
    
    while [ $attempt -lt $max_attempts ]; do
        local status=$(gh run list --limit 1 --json status --jq '.[0].status')
        local conclusion=$(gh run list --limit 1 --json conclusion --jq '.[0].conclusion')
        
        if [[ "$status" == "completed" ]]; then
            if [[ "$conclusion" == "success" ]]; then
                print_success "GitHub Actions completed successfully"
                return 0
            else
                print_error "GitHub Actions failed with conclusion: $conclusion"
                print_status "View the run details:"
                gh run list --limit 1
                return 1
            fi
        fi
        
        print_status "GitHub Actions still running... (attempt $((attempt+1))/$max_attempts)"
        sleep 30
        ((attempt++))
    done
    
    print_error "Timeout waiting for GitHub Actions to complete"
    return 1
}

# Function to verify PyPI publication
verify_pypi_publication() {
    local version=$1
    
    print_status "Verifying PyPI publication..."
    sleep 30  # Give PyPI time to process the upload
    
    # Try to check if the package exists on PyPI
    if command_exists pip; then
        print_status "Checking if apple-search-ads-client==$version is available on PyPI..."
        if pip index versions apple-search-ads-client 2>/dev/null | grep -q "$version"; then
            print_success "Package version $version found on PyPI"
        else
            print_warning "Package version $version not yet visible on PyPI (may take a few minutes)"
            print_status "You can check manually at: https://pypi.org/project/apple-search-ads-client/$version/"
        fi
    else
        print_warning "pip not found, cannot verify PyPI publication"
        print_status "Check manually at: https://pypi.org/project/apple-search-ads-client/$version/"
    fi
}

# Function to create GitHub release
create_github_release() {
    local version=$1
    
    print_status "Creating GitHub release..."
    
    # Generate release notes
    local release_notes="## Release v$version

### Changes
$(git log --oneline $(git describe --tags --abbrev=0 HEAD~1)..HEAD | sed 's/^/- /')

### Installation
\`\`\`bash
pip install apple-search-ads-client==$version
\`\`\`

### PyPI Package
- 📦 [PyPI Package](https://pypi.org/project/apple-search-ads-client/$version/)
- 📋 [Changelog](https://github.com/bickster/apple-search-ads-python/blob/main/CHANGELOG.md)

---
🤖 Generated with [Claude Code](https://claude.ai/code)"
    
    gh release create "v$version" \
        --title "Release v$version" \
        --notes "$release_notes" \
        --latest
    
    print_success "GitHub release created: https://github.com/bickster/apple-search-ads-python/releases/tag/v$version"
}

# Main function
main() {
    echo -e "${BLUE}=== Apple Search Ads Python Client Release Script ===${NC}"
    echo
    
    # Check if version argument is provided
    if [[ $# -ne 1 ]]; then
        print_error "Usage: $0 <version>"
        print_error "Example: $0 1.0.4"
        exit 1
    fi
    
    local version=$1
    
    # Check prerequisites
    print_status "Checking prerequisites..."
    
    if ! command_exists git; then
        print_error "git is required but not installed"
        exit 1
    fi
    
    if ! command_exists gh; then
        print_error "GitHub CLI (gh) is required but not installed"
        print_error "Install it with: brew install gh"
        exit 1
    fi
    
    # Check if we're in a git repository
    if ! git rev-parse --git-dir > /dev/null 2>&1; then
        print_error "Not in a git repository"
        exit 1
    fi
    
    # Check GitHub CLI authentication
    if ! gh auth status > /dev/null 2>&1; then
        print_error "GitHub CLI is not authenticated. Run: gh auth login"
        exit 1
    fi
    
    print_success "Prerequisites check passed"
    echo
    
    # Validation steps
    print_status "=== VALIDATION PHASE ==="
    validate_version "$version"
    check_version_exists "$version"
    check_git_status
    echo
    
    # Show what will be done
    echo -e "${YELLOW}=== RELEASE PLAN ===${NC}"
    echo "Version: $version"
    echo "Tag: v$version"
    echo "Actions:"
    echo "  1. Update version in setup.py and pyproject.toml"
    echo "  2. Run tests and code quality checks"
    echo "  3. Create commit and tag"
    echo "  4. Push to GitHub"
    echo "  5. Wait for GitHub Actions (tests + PyPI publish + GitHub release)"
    echo "  6. Verify PyPI publication"
    echo
    
    confirm "Proceed with release?"
    echo
    
    # Update version
    print_status "=== VERSION UPDATE PHASE ==="
    update_version "$version"
    verify_version_consistency "$version"
    echo
    
    # Quality checks
    print_status "=== QUALITY CHECKS PHASE ==="
    run_tests
    run_linting
    echo
    
    # Git operations
    print_status "=== GIT OPERATIONS PHASE ==="
    create_commit "$version"
    create_tag "$version"
    echo
    
    # Wait for CI/CD
    print_status "=== CI/CD VERIFICATION PHASE ==="
    if wait_for_actions "$version"; then
        print_success "All CI/CD checks passed"
    else
        print_error "CI/CD checks failed"
        confirm "Continue with release creation anyway?"
    fi
    echo
    
    # GitHub release will be created automatically by workflow
    print_status "=== GITHUB RELEASE PHASE ==="
    print_success "GitHub release will be created automatically by the workflow"
    echo
    
    # Verify PyPI
    print_status "=== PYPI VERIFICATION PHASE ==="
    verify_pypi_publication "$version"
    echo
    
    # Final summary
    echo -e "${GREEN}=== RELEASE COMPLETE ===${NC}"
    print_success "Release v$version completed successfully!"
    echo
    echo "📦 PyPI: https://pypi.org/project/apple-search-ads-client/$version/"
    echo "🎉 GitHub: https://github.com/bickster/apple-search-ads-python/releases/tag/v$version"
    echo "📋 Actions: https://github.com/bickster/apple-search-ads-python/actions"
    echo "⏳ Note: GitHub release creation is automatic and may take a few minutes to appear"
    echo
    print_status "Installation command: pip install apple-search-ads-client==$version"
}

# Run main function with all arguments
main "$@"