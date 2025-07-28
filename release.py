#!/usr/bin/env python3

import argparse
import re
import subprocess
import sys

def update_version_in_pyproject(version):
    with open('pyproject.toml', 'r') as f:
        content = f.read()
    
    # Update version using regex
    new_content = re.sub(
        r'version = "[0-9]+\.[0-9]+\.[0-9]+"',
        f'version = "{version}"',
        content
    )
    
    with open('pyproject.toml', 'w') as f:
        f.write(new_content)

def run_command(command, error_message):
    try:
        subprocess.run(command, check=True)
    except subprocess.CalledProcessError:
        print(f"Error: {error_message}")
        sys.exit(1)

def main():
    parser = argparse.ArgumentParser(description='Release a new version of the package')
    parser.add_argument('version', help='Version number (e.g., 1.0.7)')
    args = parser.parse_args()
    
    version = args.version
    
    # Update version in pyproject.toml
    update_version_in_pyproject(version)
    print(f"Updated version to {version} in pyproject.toml")
    
    # Commit the version change
    run_command(['git', 'add', 'pyproject.toml'], 
                "Failed to stage pyproject.toml")
    run_command(['git', 'commit', '-m', f"Bump version to {version}"], 
                "Failed to commit version change")
    
    # Create and push tag
    tag = f"v{version}"
    run_command(['git', 'tag', '-a', tag, '-m', f"Release version {version}"], 
                "Failed to create git tag")
    run_command(['git', 'push', 'origin', tag], 
                "Failed to push tag")
    run_command(['git', 'push', 'origin', 'main'], 
                "Failed to push to main branch")
    
    # Create GitHub release
    run_command(['gh', 'release', 'create', tag, 
                '--title', f"Release {version}", 
                '--notes', f"Release version {version}"], 
                "Failed to create GitHub release")
    
    print(f"Released version {version} successfully!")

if __name__ == "__main__":
    main()
