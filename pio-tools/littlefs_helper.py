#!/usr/bin/env python3
"""
LittleFS Helper Script for Tasmota

This script provides helper functions for working with LittleFS images
using littlefs-python.

Usage:
    python littlefs_helper.py create <source_dir> <output_image> --size 3MB
    python littlefs_helper.py extract <input_image> <output_dir>
    python littlefs_helper.py list <input_image>
"""

import argparse
import sys
from pathlib import Path
from littlefs import LittleFS


def parse_size(size_str):
    """Parse size string like '3MB', '0x300000', '1048576'"""
    size_str = str(size_str).lower()
    
    if size_str.startswith("0x"):
        return int(size_str, 16)
    
    multipliers = {
        'kb': 1024,
        'mb': 1024 * 1024,
        'gb': 1024 * 1024 * 1024,
    }
    
    for suffix, multiplier in multipliers.items():
        if size_str.endswith(suffix):
            num = size_str[:-len(suffix)]
            return int(num) * multiplier
    
    if size_str.endswith('b'):
        size_str = size_str[:-1]
    
    return int(size_str)


def create_image(source_dir, output_file, fs_size, block_size=4096, verbose=False):
    """Create a LittleFS image from a directory"""
    source = Path(source_dir)
    if not source.exists():
        print(f"Error: Source directory '{source_dir}' does not exist")
        return False
    
    # Berechne Block-Count
    block_count = fs_size // block_size
    if block_count * block_size != fs_size:
        print(f"Warning: fs_size ({fs_size}) is not a multiple of block_size ({block_size})")
        block_count = (fs_size + block_size - 1) // block_size
        print(f"Adjusted block_count to {block_count}")
    
    if verbose:
        print(f"Creating LittleFS image:")
        print(f"  Source:      {source}")
        print(f"  Output:      {output_file}")
        print(f"  Size:        {fs_size} bytes ({fs_size / (1024*1024):.2f} MB)")
        print(f"  Block Size:  {block_size}")
        print(f"  Block Count: {block_count}")
    
    try:
        # Create LittleFS instance
        fs = LittleFS(
            block_size=block_size,
            block_count=block_count,
            mount=True
        )
        
        # Add all files
        if source.is_dir():
            for item in source.rglob("*"):
                rel_path = item.relative_to(source)
                if item.is_dir():
                    if verbose:
                        print(f"  Creating directory: {rel_path}")
                    fs.makedirs(rel_path.as_posix(), exist_ok=True)
                else:
                    if verbose:
                        print(f"  Adding file: {rel_path} ({item.stat().st_size} bytes)")
                    # Ensure parent directories exist
                    if rel_path.parent != Path("."):
                        fs.makedirs(rel_path.parent.as_posix(), exist_ok=True)
                    # Copy file
                    with fs.open(rel_path.as_posix(), "wb") as dest:
                        dest.write(item.read_bytes())
        else:
            # Single file
            if verbose:
                print(f"  Adding file: {source.name}")
            with fs.open(source.name, "wb") as dest:
                dest.write(source.read_bytes())
        
        # Write image
        output_path = Path(output_file)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, "wb") as f:
            f.write(fs.context.buffer)
        
        if verbose:
            print(f"\nImage created successfully: {output_file}")
            print(f"Used blocks: {fs.used_block_count} / {block_count}")
        
        return True
        
    except Exception as e:
        print(f"Error creating image: {e}")
        import traceback
        traceback.print_exc()
        return False


def extract_image(input_file, output_dir, block_size=4096, verbose=False):
    """Extract a LittleFS image to a directory"""
    input_path = Path(input_file)
    if not input_path.exists():
        print(f"Error: Input file '{input_file}' does not exist")
        return False
    
    # Lese Image
    with open(input_path, "rb") as f:
        fs_data = f.read()
    
    # Berechne Block-Count
    fs_size = len(fs_data)
    block_count = fs_size // block_size
    
    if verbose:
        print(f"Extracting LittleFS image:")
        print(f"  Input:       {input_file}")
        print(f"  Output:      {output_dir}")
        print(f"  Size:        {fs_size} bytes ({fs_size / (1024*1024):.2f} MB)")
        print(f"  Block Size:  {block_size}")
        print(f"  Block Count: {block_count}")
    
    try:
        # Mounte Image
        fs = LittleFS(
            block_size=block_size,
            block_count=block_count,
            mount=False
        )
        fs.context.buffer = bytearray(fs_data)
        fs.mount()
        
        # Extract all files
        output_path = Path(output_dir)
        output_path.mkdir(parents=True, exist_ok=True)
        
        for root, dirs, files in fs.walk("/"):
            if not root.endswith("/"):
                root += "/"
            
            # Create directories
            for dir_name in dirs:
                src_path = root + dir_name
                dst_path = output_path / src_path[1:]  # Entferne führendes '/'
                if verbose:
                    print(f"  Creating directory: {dst_path}")
                dst_path.mkdir(parents=True, exist_ok=True)
            
            # Extract files
            for file_name in files:
                src_path = root + file_name
                dst_path = output_path / src_path[1:]  # Entferne führendes '/'
                dst_path.parent.mkdir(parents=True, exist_ok=True)
                
                with fs.open(src_path, "rb") as src:
                    content = src.read()
                    if verbose:
                        print(f"  Extracting file: {dst_path} ({len(content)} bytes)")
                    dst_path.write_bytes(content)
        
        fs.unmount()
        
        if verbose:
            print(f"\nExtraction completed successfully")
        
        return True
        
    except Exception as e:
        print(f"Error extracting image: {e}")
        import traceback
        traceback.print_exc()
        return False


def list_image(input_file, block_size=4096, verbose=False):
    """List the contents of a LittleFS image"""
    input_path = Path(input_file)
    if not input_path.exists():
        print(f"Error: Input file '{input_file}' does not exist")
        return False
    
    # Read image
    with open(input_path, "rb") as f:
        fs_data = f.read()
    
    # Calculate block count
    fs_size = len(fs_data)
    block_count = fs_size // block_size
    
    if verbose:
        print(f"LittleFS image information:")
        print(f"  File:        {input_file}")
        print(f"  Size:        {fs_size} bytes ({fs_size / (1024*1024):.2f} MB)")
        print(f"  Block Size:  {block_size}")
        print(f"  Block Count: {block_count}")
        print()
    
    try:
        # Mount image
        fs = LittleFS(
            block_size=block_size,
            block_count=block_count,
            mount=False
        )
        fs.context.buffer = bytearray(fs_data)
        fs.mount()
        
        if verbose:
            print(f"Used blocks: {fs.used_block_count} / {block_count}")
            print()
        
        print("Contents:")
        for root, dirs, files in fs.walk("/"):
            if not root.endswith("/"):
                root += "/"
            
            for dir_name in dirs:
                path = root + dir_name
                print(f"  [DIR]  {path}")
            
            for file_name in files:
                path = root + file_name
                stat = fs.stat(path)
                print(f"  [FILE] {path} ({stat.size} bytes)")
        
        fs.unmount()
        return True
        
    except Exception as e:
        print(f"Error listing image: {e}")
        import traceback
        traceback.print_exc()
        return False


def main():
    parser = argparse.ArgumentParser(
        description="LittleFS Helper for Tasmota",
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    
    subparsers = parser.add_subparsers(dest='command', help='Available commands')
    
    # Create command
    create_parser = subparsers.add_parser('create', help='Create LittleFS image')
    create_parser.add_argument('source', help='Source directory or file')
    create_parser.add_argument('output', help='Output image file')
    create_parser.add_argument('--size', required=True, help='Filesystem size (e.g. 3MB, 0x300000)')
    create_parser.add_argument('--block-size', type=int, default=4096, help='Block size (default: 4096)')
    create_parser.add_argument('-v', '--verbose', action='store_true', help='Verbose output')
    
    # Extract command
    extract_parser = subparsers.add_parser('extract', help='Extract LittleFS image')
    extract_parser.add_argument('input', help='Input image file')
    extract_parser.add_argument('output', help='Output directory')
    extract_parser.add_argument('--block-size', type=int, default=4096, help='Block size (default: 4096)')
    extract_parser.add_argument('-v', '--verbose', action='store_true', help='Verbose output')
    
    # List command
    list_parser = subparsers.add_parser('list', help='List LittleFS image contents')
    list_parser.add_argument('input', help='Input image file')
    list_parser.add_argument('--block-size', type=int, default=4096, help='Block size (default: 4096)')
    list_parser.add_argument('-v', '--verbose', action='store_true', help='Verbose output')
    
    args = parser.parse_args()
    
    if not args.command:
        parser.print_help()
        return 1
    
    if args.command == 'create':
        fs_size = parse_size(args.size)
        success = create_image(args.source, args.output, fs_size, args.block_size, args.verbose)
    elif args.command == 'extract':
        success = extract_image(args.input, args.output, args.block_size, args.verbose)
    elif args.command == 'list':
        success = list_image(args.input, args.block_size, args.verbose)
    else:
        parser.print_help()
        return 1
    
    return 0 if success else 1


if __name__ == '__main__':
    sys.exit(main())
