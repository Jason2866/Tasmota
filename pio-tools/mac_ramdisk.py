import subprocess
import re
import platform
import os
from pathlib import Path
import shutil

Import("env")
env = DefaultEnvironment()
os_name = platform.system()

if os_name == "Darwin":
    class MacOSRamDisk:
        """
        Class to manage RamDisk on macOS
        """
        def __init__(self, size_mb=64, name="RAMDisk", filesystem="APFS"):
            """
            Initialize RamDisk configuration
            
            Args:
                size_mb (int): Size of RamDisk in megabytes
                name (str): Name of the RamDisk volume
                filesystem (str): Filesystem type (HFS+ or APFS)
            """
            self.size_mb = size_mb
            self.name = name
            self.filesystem = filesystem
            self.device = None
            self.mount_path = None
        
        def find_existing_ramdisk(self):
            """
            Search for existing RamDisk on the system
            
            Returns:
                str: Mount path of existing RamDisk or None if not found
            """
            try:
                # Get list of all disks
                disk_list = subprocess.check_output(['diskutil', 'list'], text=True)
                disks = re.findall(r'/dev/(disk\d+)', disk_list)
                
                for disk in disks:
                    try:
                        # Get detailed information for each disk
                        info = subprocess.check_output(['diskutil', 'info', f'/dev/{disk}'], text=True)
                        
                        # Enhanced check for RamDisk properties
                        is_ramdisk = any([
                            re.search(r'Device Location.*RAM', info, re.I),
                            re.search(r'Protocol.*Virtual', info, re.I),
                            re.search(r'Virtual.*Yes', info, re.I),
                            re.search(r'RAM Disk', info, re.I)
                        ])
                        
                        if is_ramdisk:
                            # Get mount path
                            mount_output = subprocess.check_output(['mount'], text=True)
                            for line in mount_output.splitlines():
                                if f'/dev/{disk}' in line:
                                    path_match = re.search(r'on\s(/Volumes/[^\s]+)', line)
                                    if path_match:
                                        self.device = f'/dev/{disk}'
                                        self.mount_path = path_match.group(1)
                                        return self.mount_path
                    except subprocess.CalledProcessError:
                        # Disk might not be accessible, continue to next
                        continue
                return None
            except Exception as e:
                print(f'Error searching for RamDisk: {e}')
                return None
        
        def create_ramdisk(self):
            """
            Create a new RamDisk
            
            Returns:
                str: Mount path of created RamDisk or None if creation failed
            """
            # Convert MB to 512-byte sectors (macOS uses this unit)
            sectors = self.size_mb * 2048
            
            try:
                # Create RamDisk device (unmounted)
                device_output = subprocess.check_output(
                    ['hdiutil', 'attach', '-nomount', f'ram://{sectors}'], 
                    text=True
                )
                self.device = device_output.strip()
                
                # Format and mount the RamDisk
                subprocess.check_call([
                    'diskutil', 'erasevolume', self.filesystem, self.name, self.device
                ])
                
                # Determine mount path
                mount_output = subprocess.check_output(['mount'], text=True)
                for line in mount_output.splitlines():
                    if self.device in line:
                        path_match = re.search(r'on\s(/Volumes/[^\s]+)', line)
                        if path_match:
                            self.mount_path = path_match.group(1)
                            return self.mount_path
                return None
            except Exception as e:
                print(f'Error creating RamDisk: {e}')
                return None
        
        def get_ramdisk_path(self):
            """
            Main method: Get RamDisk path or create new one
            
            Returns:
                str: Path to RamDisk
                
            Raises:
                RuntimeError: If RamDisk cannot be found or created
            """
            # First search for existing RamDisk
            existing_path = self.find_existing_ramdisk()
            if existing_path:
                print(f'Found existing RamDisk: {existing_path}')
                return existing_path
            
            # Create new RamDisk
            print(f'Creating new RamDisk ({self.size_mb} MB)...')
            new_path = self.create_ramdisk()
            if new_path:
                print(f'RamDisk created: {new_path}')
                return new_path
            else:
                raise RuntimeError('Failed to create RamDisk')
        
        def get_ramdisk_info(self):
            """
            Get detailed information about the RamDisk
            
            Returns:
                dict: Dictionary with RamDisk information
            """
            if not self.device:
                return None
                
            try:
                info = subprocess.check_output(['diskutil', 'info', self.device], text=True)
                return {
                    'device': self.device,
                    'mount_path': self.mount_path,
                    'size_mb': self.size_mb,
                    'filesystem': self.filesystem,
                    'name': self.name,
                    'raw_info': info
                }
            except Exception as e:
                print(f'Error getting RamDisk info: {e}')
                return None
        
        def cleanup(self):
            """
            Detach and remove the RamDisk
            """
            if self.device:
                try:
                    subprocess.check_call(['hdiutil', 'detach', self.device])
                    print(f'RamDisk {self.device} detached successfully')
                    self.device = None
                    self.mount_path = None
                except Exception as e:
                    print(f'Error detaching RamDisk: {e}')
        
        def __enter__(self):
            """Context manager entry"""
            return self.get_ramdisk_path()
        
        def __exit__(self, exc_type, exc_val, exc_tb):
            """Context manager exit - cleanup RamDisk"""
            self.cleanup()




# Configuration
RAMDISK_SIZE_MB = 1024  # Size in MB
RAMDISK_NAME = "RAMDisk"

try:
    ramdisk = MacOSRamDisk(size_mb=RAMDISK_SIZE_MB, name=RAMDISK_NAME)
    path = ramdisk.get_ramdisk_path()
    # Get detailed information
    info = ramdisk.get_ramdisk_info()
    if info:
        print(f'Device: {info["device"]}')
        print(f'Size: {info["size_mb"]} MB')
        print(f'Filesystem: {info["filesystem"]}')

    if path:
        path_build_cache = Path(env.GetProjectConfig().get("platformio", "build_cache_dir"))
        print(f'Config build_cache_dir: {path_build_cache}')
        if path_build_cache.exists():
            if path_build_cache.is_symlink():
                path_build_cache.unlink()
            else:
                shutil.rmtree(path_build_cache)

        ramdisk_build_cache_dir = Path(path) / ".cache"
        ramdisk_build_cache_dir.mkdir(parents=True, exist_ok=True)
        os.symlink(str(ramdisk_build_cache_dir), path_build_cache)
        print(f'Symlink created: {path_build_cache} -> {ramdisk_build_cache_dir}')

        path_build_dir = Path(env.GetProjectConfig().get("platformio", "build_dir"))
        print(f'Config build_dir: {path_build_dir}')
        if path_build_dir.exists():
            if path_build_dir.is_symlink():
                path_build_dir.unlink()
            else:
                shutil.rmtree(path_build_dir)

        ramdisk_build_dir = Path(path) / ".pio" / "build"
        ramdisk_build_dir.mkdir(parents=True, exist_ok=True)
        os.symlink(str(ramdisk_build_dir), path_build_dir)
        print(f'Symlink created: {path_build_dir} -> {ramdisk_build_dir}')

        # Optional: Clean up (uncomment to remove RamDisk)
#        ramdisk.cleanup()
        
except Exception as e:
    print(f'Error: {e}')
    