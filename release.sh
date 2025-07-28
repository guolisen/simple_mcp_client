#!/bin/bash

# Check if version argument is provided
if [ $# -ne 1 ]; then
    echo "Usage: $0 <version>"
    echo "Example: $0 1.0.7"
    exit 1
fi

VERSION=$1

# Update version in pyproject.toml
sed -i "s/version = \"[0-9]*\.[0-9]*\.[0-9]*\"/version = \"$VERSION\"/" pyproject.toml

# Commit the version change
git add pyproject.toml
git commit -m "Bump version to $VERSION"

# Create and push tag
git tag -a "v$VERSION" -m "Release version $VERSION"
git push origin "v$VERSION"
git push origin main

# Create GitHub release
gh release create "v$VERSION" --title "Release $VERSION" --notes "Release version $VERSION"

echo "Released version $VERSION successfully!"
