#!/bin/bash
# Cleanup broken symlinks in media folders

echo "=== Torplex Symlink Cleanup ==="
echo ""

MEDIA_DIR="/data/media"

# Count broken symlinks
BROKEN_COUNT=$(find "$MEDIA_DIR" -type l ! -exec test -e {} \; -print 2>/dev/null | wc -l)

echo "Found $BROKEN_COUNT broken symlinks in $MEDIA_DIR"
echo ""

if [ "$BROKEN_COUNT" -gt 0 ]; then
    echo "Broken symlinks:"
    find "$MEDIA_DIR" -type l ! -exec test -e {} \; -print 2>/dev/null | head -20
    echo ""
    
    if [ "$1" == "--delete" ]; then
        echo "Deleting broken symlinks..."
        find "$MEDIA_DIR" -type l ! -exec test -e {} \; -delete 2>/dev/null
        echo "Done! Deleted $BROKEN_COUNT broken symlinks."
    else
        echo "Run with --delete to remove broken symlinks:"
        echo "  ./cleanup_symlinks.sh --delete"
    fi
else
    echo "No broken symlinks found. All good!"
fi
