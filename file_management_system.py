import tkinter as tk
from tkinter import ttk, simpledialog, messagebox, font
from datetime import datetime
import random
import json
import os
import copy
import platform
import sys
import subprocess
import tempfile
import webbrowser

# Initialize TTKBOOTSTRAP_AVAILABLE first
TTKBOOTSTRAP_AVAILABLE = False

# Try to import ttkbootstrap for theming
try:
    import ttkbootstrap as ttk_bs
    from ttkbootstrap import Style
    TTKBOOTSTRAP_AVAILABLE = True
    print("ttkbootstrap is available")
except ImportError:
    TTKBOOTSTRAP_AVAILABLE = False
    print("ttkbootstrap not available - using default tkinter themes")
except Exception as e:
    TTKBOOTSTRAP_AVAILABLE = False
    print(f"Error importing ttkbootstrap: {e}")

# Try to import PIL, but don't fail if it's not available
try:
    from PIL import Image, ImageTk
    PIL_AVAILABLE = True
except ImportError:
    PIL_AVAILABLE = False
    print("PIL not available - running without image support")

# Constants
MAX_FILES = 100
MAX_DIRS = 50
MAX_BLOCKS = 1000
SAVE_FILE_PATH = "file_system_state.json"
 

# Allocation & Role Definitions
class AllocationMethod:
    CONTIGUOUS = "Contiguous"
    LINKED = "Linked"
    INDEXED = "Indexed"

class UserRole:
    USER = "USER"
    ADMIN = "ADMIN"


user_list = [
    {"username": "admin", "role": UserRole.ADMIN}
]
current_user = {"username": "admin", "role": UserRole.ADMIN}


# Clipboard for cut/copy/paste operations
clipboard = {
    "items": [],  # List of items (files/directories)
    "operation": None,  # "cut" or "copy"
    "source_directory": None  # Source directory for cut operations
}

# File system structure
class File:
    def __init__(self, name, allocation="Contiguous", permissions=1):
        self.name = name
        self.start_block = random.randint(1, MAX_BLOCKS - 10)
        self.block_count = 0
        self.permissions = permissions  # 0 = read-only, 1 = read-write
        self.allocation = allocation
        self.content = ""
        self.timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")
        self.size_bytes = 0
        self.original_location = None  # Store original location for trash restore

    def update_size_and_allocation(self):
        """Automatically update file size and allocation method based on content"""
        if self.content:
            # Calculate size in bytes (assuming 1 character = 1 byte)
            self.size_bytes = len(self.content.encode('utf-8'))
            
            # Calculate blocks needed (assuming 512 bytes per block)
            bytes_per_block = 512
            blocks_needed = max(1, (self.size_bytes + bytes_per_block - 1) // bytes_per_block)
            
            # Auto-select allocation method based on size
            if blocks_needed == 1:
                self.allocation = "Contiguous"
                self.block_count = 1
            elif blocks_needed <= 5:
                self.allocation = "Contiguous"  # Small files use contiguous
                self.block_count = blocks_needed
            elif blocks_needed <= 20:
                self.allocation = "Linked"  # Medium files use linked
                self.block_count = blocks_needed
            else:
                self.allocation = "Indexed"  # Large files use indexed
                self.block_count = blocks_needed
        else:
            # Empty file
            self.size_bytes = 0
            self.block_count = 0
            self.allocation = "Contiguous"  # Default for empty files
    
    def add_content(self, new_content):
        """Add content to file and automatically update size/allocation"""
        self.content += new_content
        self.update_size_and_allocation()
        self.timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")
    
    def set_content(self, new_content):
        """Set file content and automatically update size/allocation"""
        self.content = new_content
        self.update_size_and_allocation()
        self.timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")
    
    def get_size_display(self):
        """Get human-readable file size"""
        if self.size_bytes == 0:
            return "0 bytes"
        elif self.size_bytes < 1024:
            return f"{self.size_bytes} bytes"
        elif self.size_bytes < 1024 * 1024:
            return f"{self.size_bytes / 1024:.1f} KB"
        else:
            return f"{self.size_bytes / (1024 * 1024):.1f} MB"
    
    def to_dict(self):
        return {
            "name": self.name,
            "start_block": self.start_block,
            "block_count": self.block_count,
            "permissions": self.permissions,
            "allocation": self.allocation,
            "content": self.content,
            "timestamp": self.timestamp,
            "size_bytes": self.size_bytes,
            "original_location": self.original_location
        }
    
    @classmethod
    def from_dict(cls, data):
        file = cls(data["name"], data.get("allocation", "Contiguous"), data["permissions"])
        file.start_block = data["start_block"]
        file.block_count = data.get("block_count", 0)
        file.content = data["content"]
        file.timestamp = data["timestamp"]
        file.size_bytes = data.get("size_bytes", 0)
        file.original_location = data.get("original_location", None)
        # Update allocation based on current content
        file.update_size_and_allocation()
        return file

class Directory:
    def __init__(self, name):
        self.name = name
        self.files = []
        self.subdirectories = []
        self.timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")
        self.original_location = None  # Store original location for trash restore
        self.original_parent = None    # Store original parent directory for trash restore

    def create_file(self, filename, allocation, permissions):
        if len(self.files) >= MAX_FILES:
            return "Error: Directory full."
        if any(f.name == filename for f in self.files):
            return "Error: File already exists."
        self.files.append(File(filename, allocation, permissions))
        return f"File '{filename}' created."

    def delete_file(self, filename):
        if current_user["role"] != UserRole.ADMIN:
            return "Error: Only ADMIN can delete."
        for file in self.files:
            if file.name == filename:
                if file.permissions == 0:
                    return "Error: Read-Only file."
                # Store original location for restore functionality
                file.original_location = self.name
                trash_dir.files.append(file)
                self.files.remove(file)
                return f"File '{filename}' moved to trash."
        return "Error: File not found."

    def restore_file(self, filename):
        """Restore a file from trash to its original location"""
        if self.name != "Trash":
            return "Error: Can only restore from Trash."
        
        for file in self.files:
            if file.name == filename:
                if not file.original_location:
                    return "Error: Original location unknown."
                
                # Find the original directory
                original_dir = find_directory(file.original_location)
                if not original_dir:
                    return f"Error: Original directory '{file.original_location}' not found."
                
                # Check if file with same name already exists in original location
                if any(f.name == filename for f in original_dir.files):
                    return f"Error: File '{filename}' already exists in '{file.original_location}'."
                
                # Move file back to original location
                file.original_location = None  # Clear the trash marker
                original_dir.files.append(file)
                self.files.remove(file)
                return f"File '{filename}' restored to '{original_dir.name}'."
        return "Error: File not found in trash."

    def delete_file_permanently(self, filename):
        """Permanently delete a file from trash"""
        if self.name != "Trash":
            return "Error: Can only permanently delete from Trash."
        
        for file in self.files:
            if file.name == filename:
                self.files.remove(file)
                return f"File '{filename}' permanently deleted."
        return "Error: File not found in trash."

    def create_subdirectory(self, dirname):
        if len(self.subdirectories) >= MAX_DIRS:
            return "Error: Directory limit reached."
        if any(d.name == dirname for d in self.subdirectories):
            return "Error: Directory already exists."
        self.subdirectories.append(Directory(dirname))
        return f"Directory '{dirname}' created."

    def delete_subdirectory(self, dirname):
        """Move subdirectory to trash instead of permanent deletion"""
        if current_user["role"] != UserRole.ADMIN:
            return "Error: Only ADMIN can delete."
        
        for subdir in self.subdirectories:
            if subdir.name == dirname:
                # Store original location and parent for restore functionality
                subdir.original_location = self.name
                subdir.original_parent = self
                trash_dir.subdirectories.append(subdir)
                self.subdirectories.remove(subdir)
                return f"Directory '{dirname}' moved to trash."
        return "Error: Directory not found."

    def restore_directory(self, dirname):
        """Restore a directory from trash to its original location"""
        if self.name != "Trash":
            return "Error: Can only restore from Trash."
        
        for directory in self.subdirectories:
            if directory.name == dirname:
                if not directory.original_parent:
                    return "Error: Original location unknown."
                
                # Check if directory with same name already exists in original location
                if any(d.name == dirname for d in directory.original_parent.subdirectories):
                    return f"Error: Directory '{dirname}' already exists in original location."
                
                # Move directory back to original location
                directory.original_parent.subdirectories.append(directory)
                directory.original_location = None
                directory.original_parent = None
                self.subdirectories.remove(directory)
                return f"Directory '{dirname}' restored to original location."
        return "Error: Directory not found in trash."

    def delete_directory_permanently(self, dirname):
        """Permanently delete a directory from trash"""
        if self.name != "Trash":
            return "Error: Can only permanently delete from Trash."
        
        for directory in self.subdirectories:
            if directory.name == dirname:
                self.subdirectories.remove(directory)
                return f"Directory '{dirname}' permanently deleted."
        return "Error: Directory not found in trash."

    def rename_file(self, old_name, new_name):
        for file in self.files:
            if file.name == old_name:
                if any(f.name == new_name for f in self.files):
                    return "Error: File with new name already exists."
                file.name = new_name
                return f"File renamed from '{old_name}' to '{new_name}'."
        return "Error: File not found."

    def rename_subdirectory(self, old_name, new_name):
        for subdir in self.subdirectories:
            if subdir.name == old_name:
                if any(d.name == new_name for d in self.subdirectories):
                    return "Error: Directory with new name already exists."
                subdir.name = new_name
                return f"Directory renamed from '{old_name}' to '{new_name}'."
        return "Error: Directory not found."

    def empty_trash(self):
        """Empty trash - delete all files and directories permanently"""
        if self.name == "Trash":
            self.files.clear()
            self.subdirectories.clear()
            return "Trash is now empty."
        return "Error: Not Trash directory."
    
    def to_dict(self):
        return {
            "name": self.name,
            "files": [file.to_dict() for file in self.files],
            "subdirectories": [subdir.to_dict() for subdir in self.subdirectories],
            "timestamp": self.timestamp,
            "original_location": self.original_location,
            "original_parent": None  # Can't serialize parent reference
        }
    
    @classmethod
    def from_dict(cls, data):
        directory = cls(data["name"])
        directory.files = [File.from_dict(file_data) for file_data in data["files"]]
        directory.subdirectories = [Directory.from_dict(subdir_data) for subdir_data in data["subdirectories"]]
        directory.timestamp = data["timestamp"]
        directory.original_location = data.get("original_location", None)
        # original_parent will be rebuilt during loading
        return directory

# Clipboard operations
def clear_clipboard():
    """Clear the clipboard"""
    clipboard["items"] = []
    clipboard["operation"] = None
    clipboard["source_directory"] = None

def copy_to_clipboard(items, operation, source_dir):
    """Copy items to clipboard"""
    clipboard["items"] = items
    clipboard["operation"] = operation
    clipboard["source_directory"] = source_dir

def can_paste_here(target_directory):
    """Check if we can paste in the target directory"""
    if not clipboard["items"] or not target_directory:
        return False
    
    # Check for name conflicts
    for item in clipboard["items"]:
        # Check if file with same name exists
        if hasattr(item, 'content'):  # It's a file
            if any(f.name == item.name for f in target_directory.files):
                return False
        else:  # It's a directory
            if any(d.name == item.name for d in target_directory.subdirectories):
                return False
            # Prevent circular reference (moving directory into itself or its subdirectory)
            if clipboard["operation"] == "cut" and is_subdirectory_of(target_directory, item):
                return False
    
    return True

def is_subdirectory_of(potential_child, potential_parent):
    """Check if potential_child is a subdirectory of potential_parent"""
    if potential_child == potential_parent:
        return True
    
    for subdir in potential_parent.subdirectories:
        if is_subdirectory_of(potential_child, subdir):
            return True
    
    return False

def paste_items(target_directory):
    """Paste items from clipboard to target directory"""
    if not can_paste_here(target_directory):
        return "Error: Cannot paste here due to conflicts or circular reference."
    
    success_count = 0
    
    for item in clipboard["items"]:
        if hasattr(item, 'content'):  # It's a file
            if clipboard["operation"] == "cut":
                # Move file
                clipboard["source_directory"].files.remove(item)
                target_directory.files.append(item)
            else:  # copy
                # Create a deep copy of the file
                new_file = copy.deepcopy(item)
                target_directory.files.append(new_file)
            success_count += 1
        else:  # It's a directory
            if clipboard["operation"] == "cut":
                # Move directory
                clipboard["source_directory"].subdirectories.remove(item)
                target_directory.subdirectories.append(item)
            else:  # copy
                # Create a deep copy of the directory
                new_dir = copy.deepcopy(item)
                target_directory.subdirectories.append(new_dir)
            success_count += 1
    
    # Clear clipboard after any paste operation (cut or copy) - allows only one-time paste
    clear_clipboard()
    
    return f"Successfully pasted {success_count} item(s)."

trash_dir = Directory("Trash")
root_directories = [
    Directory("Documents"),
    Directory("Media"),
    Directory("Projects"),
    Directory("System"),
    trash_dir
]

def find_directory(name):
    for root in root_directories:
        found = _find_directory_recursive(root, name)
        if found:
            return found
    return None

def _find_directory_recursive(current, name):
    if current.name == name:
        return current
    for subdir in current.subdirectories:
        found = _find_directory_recursive(subdir, name)
        if found:
            return found
    return None

def save_file_system():
    """Save the file system state AND user list to a JSON file"""
    # Convert user_list to a serializable format
    serializable_user_list = []
    for user in user_list:
        serializable_user_list.append({
            "username": user["username"],
            "role": user["role"]  # UserRole enum values are strings, so they're already serializable
        })
    
    data = {
        "current_user": current_user,
        "user_list": serializable_user_list,  # Add user list to saved data
        "root_directories": [directory.to_dict() for directory in root_directories]
    }
    
    try:
        with open(SAVE_FILE_PATH, 'w') as f:
            json.dump(data, f, indent=2)
        return "File system state saved successfully."
    except Exception as e:
        return f"Error saving file system: {str(e)}"

def load_file_system():
    """Load the file system state AND user list from a JSON file"""
    global root_directories, trash_dir, current_user, user_list
    
    if not os.path.exists(SAVE_FILE_PATH):
        return "No saved state found. Starting with default file system."
    
    try:
        with open(SAVE_FILE_PATH, 'r') as f:
            data = json.load(f)
        
        # Load current user
        if "current_user" in data:
            current_user = data["current_user"]
        
        # Load user list if it exists in saved data
        if "user_list" in data:
            user_list.clear()  # Clear the default admin-only list
            for user_data in data["user_list"]:
                user_list.append({
                    "username": user_data["username"],
                    "role": user_data["role"]
                })
        else:
            # If no user_list in saved data, keep the default admin user
            print("No user list found in saved data, keeping default admin user")
        
        # Load directories
        root_directories = [Directory.from_dict(dir_data) for dir_data in data["root_directories"]]
        
        # Find the trash directory and rebuild parent references
        for directory in root_directories:
            if directory.name == "Trash":
                trash_dir = directory
                # Rebuild parent references for items in trash
                for trashed_dir in trash_dir.subdirectories:
                    if trashed_dir.original_location:
                        trashed_dir.original_parent = find_directory(trashed_dir.original_location)
                break
        
        return "File system state loaded successfully."
    except Exception as e:
        return f"Error loading file system: {str(e)}"

def open_file_with_os_application(file_obj):
    """
    Open a file with the OS default application.
    Creates a temporary file with the content and opens it.
    """
    if not file_obj:
        print("No file object provided")
        return False
    
    try:
        # Get file extension to determine the appropriate temporary file
        if '.' in file_obj.name:
            extension = '.' + file_obj.name.split('.')[-1].lower()
        else:
            extension = '.txt'  # Default to .txt for files without extension
        
        # Create a temporary file with the appropriate extension
        with tempfile.NamedTemporaryFile(mode='w', suffix=extension, delete=False, encoding='utf-8') as temp_file:
            # Write the content to the temporary file
            content = file_obj.content if file_obj.content else f"# {file_obj.name}\n\nThis file was created in the File System Explorer.\nFile Size: {file_obj.get_size_display()}\nAllocation: {file_obj.allocation}\nLast Modified: {file_obj.timestamp}\n\n"
            temp_file.write(content)
            temp_file_path = temp_file.name
        
        print(f"Created temporary file: {temp_file_path}")
        
        # Open the file with the OS default application
        system_name = platform.system().lower()
        
        if system_name == 'windows':
            # Windows - use os.startfile
            os.startfile(temp_file_path)
            print(f"Opened file with Windows default application")
            
        elif system_name == 'darwin':
            # macOS - use 'open' command
            subprocess.call(['open', temp_file_path])
            print(f"Opened file with macOS default application")
            
        else:
            # Linux/Unix - use 'xdg-open' command
            subprocess.call(['xdg-open', temp_file_path])
            print(f"Opened file with Linux default application")
        
        # Note: We're not deleting the temp file immediately because the OS application
        # might need time to open it. In a production app, you might want to implement
        # a cleanup mechanism that deletes temp files after some time.
        
        return True
        
    except Exception as e:
        print(f"Error opening file with OS application: {e}")
        messagebox.showerror("Error", f"Could not open file with system application:\n{str(e)}\n\nTrying fallback method...")
        
        # Fallback: try to open with webbrowser (works for some file types)
        try:
            webbrowser.open(temp_file_path)
            return True
        except Exception as e2:
            print(f"Fallback method also failed: {e2}")
            messagebox.showerror("Error", f"Could not open file with any available method:\n{str(e2)}")
            return False

class FileSystemApp:
    def __init__(self, master):
        self.master = master
        master.title("File System Explorer")
        master.geometry("1200x700")

        # Initialize with admin user
        self.current_directory = None
        self.selected_item = None
        self.selected_item_type = None  # 'file' or 'directory'

        # Navigation history
        self.navigation_history = []
        self.history_index = -1

        print(f"Initialized navigation: history={self.navigation_history}, index={self.history_index}")

        self.os_type = platform.system().lower()
        print(f"Detected OS: {self.os_type}")

        # Initialize theme system
        self.setup_theme_system()
        self.setup_os_specific_config()
        self.apply_dark_theme()

        self.load_icons()
        self.create_ui()
        self.setup_keyboard_shortcuts()

        # Load file system state silently - no dialog boxes
        try:
            load_file_system()
            self.refresh_user_interface_after_load()
        except Exception as e:
            print(f"Could not load saved state: {e}")
            self.refresh_user_interface_after_load()

        # Setup window close event
        master.protocol("WM_DELETE_WINDOW", self.on_close)

        # Setup auto-save (since we removed manual save button)
        self.setup_auto_save()

        self.refresh_directory_tree()
        self.update_role_display()

    def setup_theme_system(self):
        """Initialize theme system with ttkbootstrap or fallback to ttk"""
        global TTKBOOTSTRAP_AVAILABLE
        
        # Ensure TTKBOOTSTRAP_AVAILABLE is defined
        if 'TTKBOOTSTRAP_AVAILABLE' not in globals():
            TTKBOOTSTRAP_AVAILABLE = False
            
        self.current_theme = "darkly"  # Default theme
        
        if TTKBOOTSTRAP_AVAILABLE:
            print("Setting up ttkbootstrap themes...")
            # Available ttkbootstrap themes
            self.available_themes = [
                "cosmo", "flatly", "journal", "litera", "lumen", "minty",
                "pulse", "sandstone", "united", "yeti", "morph", "simplex", 
                "cerculean", "solar", "superhero", "darkly", "cyborg", "vapor"
            ]
            
            # Initialize with dark theme
            try:
                self.style = Style(theme=self.current_theme)
                print(f"ttkbootstrap theme '{self.current_theme}' applied successfully")
            except Exception as e:
                print(f"Error applying ttkbootstrap theme: {e}")
                self.style = ttk.Style()
                TTKBOOTSTRAP_AVAILABLE = False
        else:
            print("Using standard ttk themes...")
            self.style = ttk.Style()
            # Available standard ttk themes
            self.available_themes = list(self.style.theme_names())
            
            # Try to use a dark theme if available
            if "clam" in self.available_themes:
                self.current_theme = "clam"
            else:
                self.current_theme = self.available_themes[0] if self.available_themes else "default"

    def apply_theme(self, theme_name):
        """Apply a theme"""
        try:
            if TTKBOOTSTRAP_AVAILABLE:
                # Use ttkbootstrap
                self.style = Style(theme=theme_name)
                print(f"Applied ttkbootstrap theme: {theme_name}")
            else:
                # Use standard ttk
                self.style.theme_use(theme_name)
                print(f"Applied ttk theme: {theme_name}")
            
            self.current_theme = theme_name
            
            # IMPORTANT: Reapply our custom treeview styling after theme change
            self.apply_custom_treeview_styling()
            
            # Refresh UI to apply theme changes
            self.refresh_after_theme_change()
            
        except Exception as e:
            print(f"Error applying theme {theme_name}: {e}")
            messagebox.showerror("Theme Error", f"Could not apply theme '{theme_name}': {e}")

    def apply_custom_treeview_styling(self):
        """Apply custom treeview styling that persists across theme changes"""
        try:
            # Force apply our custom row height and styling regardless of theme
            self.style.configure("Treeview", 
                          font=("TkDefaultFont", 11),
                          rowheight=48)  # Ensure consistent row height across all themes
            
            # Apply additional styling for better appearance
            self.style.configure("Treeview.Heading", 
                          font=("TkDefaultFont", 11, "bold"))
            
            print(f"Custom treeview styling applied for theme: {self.current_theme}")
            
        except Exception as e:
            print(f"Error applying custom treeview styling: {e}")

    def refresh_after_theme_change(self):
        """Refresh UI components after theme change"""
        try:
            # Force update all ttk widgets
            self.master.update_idletasks()
            
            # Reapply custom styling again to ensure it sticks
            self.master.after(100, self.apply_custom_treeview_styling)
            
            # Update canvas background to match new theme
            if hasattr(self, 'icon_canvas'):
                try:
                    # Get theme-appropriate canvas background
                    if TTKBOOTSTRAP_AVAILABLE:
                        canvas_bg = self.style.colors.bg if hasattr(self.style, 'colors') else "#f0f0f0"
                    else:
                        canvas_bg = "#f0f0f0" if "light" in self.current_theme.lower() or self.current_theme in ["default", "clam", "alt"] else "#2e2e2e"
                    
                    self.icon_canvas.configure(bg=canvas_bg)
                    if hasattr(self, 'icon_grid_frame'):
                        self.icon_grid_frame.configure(bg=canvas_bg)
                except:
                    pass
            
            # Refresh treeview
            if hasattr(self, 'directory_tree'):
                self.directory_tree.update()
            
            # Refresh content area
            self.refresh_content()
            
            print("UI refreshed after theme change")
        except Exception as e:
            print(f"Error refreshing UI after theme change: {e}")

    def on_theme_change(self, event=None):
        """Handle theme selection change"""
        selected_theme = self.theme_var.get()
        if selected_theme and selected_theme != self.current_theme:
            print(f"Theme changed to: {selected_theme}")
            self.apply_theme(selected_theme)
            
            # Force reapply custom styling after a short delay to ensure it takes effect
            self.master.after(200, self.apply_custom_treeview_styling)
            self.master.after(400, self.apply_custom_treeview_styling)  # Double check

    def refresh_user_interface_after_load(self):
        """Refresh user interface components after loading saved state"""
        # Update the user dropdown to reflect loaded users
        self.update_user_dropdown()

        # Update role display to show current user
        self.update_role_display()

        print(f"Loaded users: {[user['username'] for user in user_list]}")
        print(f"Current user: {current_user['username']} ({current_user['role']})")

    def setup_keyboard_shortcuts(self):
        """Setup keyboard shortcuts - updated to handle trash operations properly"""

        def safe_keyboard_cut(event):
            # Check if a text widget has focus
            focused_widget = self.master.focus_get()
            if isinstance(focused_widget, tk.Text):
                return  # Let the text widget handle it

            if self.selected_items and self.current_directory:
                # Don't allow cut in trash
                if self.current_directory.name != "Trash":
                    self.cut_selected()

        def safe_keyboard_copy(event):
            # Check if a text widget has focus
            focused_widget = self.master.focus_get()
            if isinstance(focused_widget, tk.Text):
                return  # Let the text widget handle it

            if self.selected_items and self.current_directory:
                # Don't allow copy in trash
                if self.current_directory.name != "Trash":
                    self.copy_selected()

        def safe_keyboard_paste(event):
            # Check if a text widget has focus
            focused_widget = self.master.focus_get()
            if isinstance(focused_widget, tk.Text):
                return  # Let the text widget handle it

            if self.current_directory:
                # Don't allow paste in trash
                if self.current_directory.name != "Trash":
                    self.paste_to_current()

        def safe_keyboard_delete(event):
            # Check if a text widget has focus
            focused_widget = self.master.focus_get()
            if isinstance(focused_widget, tk.Text):
                return  # Let the text widget handle it
    
            if self.selected_items and self.current_directory:
                # Handle trash differently - permanent deletion
                if self.current_directory.name == "Trash":
                    # In trash, Delete key permanently deletes
                    # Handle BOTH files AND directories in mixed selections
                    self.delete_permanently_mixed_selection()
                else:
                    # Normal deletion - move to trash
                    # Handle mixed selections properly
                    self.delete_mixed_selection_to_trash()
    
                # Clear selection after deletion
                self.clear_selection()

        def safe_keyboard_toggle_panel(event):
            self.toggle_left_panel()

        def safe_keyboard_custom_minimize(event):
            self.custom_minimize()

        def safe_keyboard_refresh(event):
            self.refresh_all()

        # Use the safe functions for keyboard shortcuts
        self.master.bind_all("<Control-x>", safe_keyboard_cut)
        self.master.bind_all("<Control-c>", safe_keyboard_copy)
        self.master.bind_all("<Control-v>", safe_keyboard_paste)
        self.master.bind_all("<Delete>", safe_keyboard_delete)
        self.master.bind_all("<F9>", safe_keyboard_toggle_panel)  # F9 to toggle left panel
        self.master.bind_all("<Control-m>", safe_keyboard_custom_minimize)  # Ctrl+M for custom minimize

    def navigate_to_directory(self, directory):
        """Navigate to a directory and update history"""
        if directory and directory != self.current_directory:
            # Add current directory to history before navigating (if we have one)
            if self.current_directory:
                # Remove any forward history when navigating to a new location
                self.navigation_history = self.navigation_history[:self.history_index + 1]
                
                # Add current directory to history
                self.navigation_history.append(self.current_directory)
                self.history_index = len(self.navigation_history) - 1
                
                print(f"Added '{self.current_directory.name}' to history. History index: {self.history_index}")
            
            # Navigate to new directory
            self.current_directory = directory
            self.current_path_label.config(text=f"Current: {self.current_directory.name}")
            
            print(f"Navigated to '{directory.name}'. Can go back: {self.history_index > 0}")
            
            # Update button states
            self.update_navigation_buttons()
            
            # Refresh content
            self.refresh_content()

    def go_back(self):
        """Navigate back in history"""
        if self.history_index >= 0 and len(self.navigation_history) > 0:
            # Get the directory to go back to
            previous_directory = self.navigation_history[self.history_index]
            
            # Move history index back
            self.history_index -= 1
            
            print(f"Going back to '{previous_directory.name}'. New history index: {self.history_index}")
            
            # Set the directory without adding to history (this is a back navigation)
            self.current_directory = previous_directory
            self.current_path_label.config(text=f"Current: {self.current_directory.name}")
            
            # Update button states and refresh content
            self.update_navigation_buttons()
            self.refresh_content()
        else:
            print("Cannot go back - no history available")

    def go_forward(self):
        """Navigate forward in history"""
        if self.history_index < len(self.navigation_history) - 1:
            # Move history index forward
            self.history_index += 1
            
            # Get the directory to go forward to
            next_directory = self.navigation_history[self.history_index]
            
            print(f"Going forward to '{next_directory.name}'. New history index: {self.history_index}")
            
            # Set the directory without adding to history (this is a forward navigation)
            self.current_directory = next_directory
            self.current_path_label.config(text=f"Current: {self.current_directory.name}")
            
            # Update button states and refresh content
            self.update_navigation_buttons()
            self.refresh_content()
        else:
            print("Cannot go forward - no forward history available")

    def update_navigation_buttons(self):
        """Update back/forward button states"""
        # Enable/disable back button
        can_go_back = self.history_index >= 0 and len(self.navigation_history) > 0
        if can_go_back:
            self.back_button.config(state=tk.NORMAL)
            print(f"Back button ENABLED. History: {[d.name for d in self.navigation_history]}, Index: {self.history_index}")
        else:
            self.back_button.config(state=tk.DISABLED)
            print(f"Back button DISABLED. History length: {len(self.navigation_history)}, Index: {self.history_index}")
        
        # Enable/disable forward button
        can_go_forward = self.history_index < len(self.navigation_history) - 1
        if can_go_forward:
            self.forward_button.config(state=tk.NORMAL)
        else:
            self.forward_button.config(state=tk.DISABLED)

    def create_ui(self):
        # Top frame for theme, navigation, role display and search
        top_frame = ttk.Frame(self.master)
        top_frame.pack(fill=tk.X, padx=10, pady=5)

        # Theme selector (top left)
        theme_frame = ttk.Frame(top_frame)
        theme_frame.pack(side=tk.LEFT, padx=(0, 20))
        
        ttk.Label(theme_frame, text="Theme:").pack(side=tk.LEFT, padx=(0, 5))
        
        self.theme_var = tk.StringVar(value=self.current_theme)
        self.theme_dropdown = ttk.Combobox(theme_frame, textvariable=self.theme_var,
                                          values=self.available_themes, state="readonly", width=10)
        self.theme_dropdown.pack(side=tk.LEFT)
        self.theme_dropdown.bind("<<ComboboxSelected>>", self.on_theme_change)

        # Navigation frame (left of center)
        nav_frame = ttk.Frame(top_frame)
        nav_frame.pack(side=tk.LEFT)

        # Back button
        self.back_button = ttk.Button(nav_frame, command=self.go_back, state=tk.DISABLED, width=4)
        if self.back_icon:
            self.back_button.config(image=self.back_icon, text="")
        else:
            self.back_button.config(text="←")
        self.back_button.pack(side=tk.LEFT, padx=2)

        # Forward button  
        self.forward_button = ttk.Button(nav_frame, command=self.go_forward, state=tk.DISABLED, width=4)
        if self.forward_icon:
            self.forward_button.config(image=self.forward_icon, text="")
        else:
            self.forward_button.config(text="→")
        self.forward_button.pack(side=tk.LEFT, padx=2)

        # Search frame (center)
        self.search_frame = ttk.Frame(top_frame)
        self.search_frame.pack(side=tk.LEFT, padx=20)

        self.search_label = ttk.Label(self.search_frame, text="Search: ")
        self.search_label.pack(side=tk.LEFT, padx=5)

        self.search_entry = ttk.Entry(self.search_frame)
        self.search_entry.pack(side=tk.LEFT, padx=5)

        self.search_button = ttk.Button(self.search_frame, text="Search", command=self.search)
        self.search_button.pack(side=tk.LEFT, padx=5)

        # User management frame (top right)
        self.user_frame = ttk.Frame(top_frame)
        self.user_frame.pack(side=tk.RIGHT)

        # User icon
        self.user_icon_label = ttk.Label(self.user_frame, image=self.admin_icon if self.admin_icon else None)
        self.user_icon_label.pack(side=tk.LEFT, padx=5)

        # User dropdown with dynamic options
        self.user_var = tk.StringVar(value="admin (ADMIN)")
        self.user_dropdown = ttk.Combobox(self.user_frame, textvariable=self.user_var, 
                                         state="readonly", width=18)
        self.update_user_dropdown()  # Initialize dropdown options
        self.user_dropdown.pack(side=tk.LEFT, padx=5)
        self.user_dropdown.bind("<<ComboboxSelected>>", self.on_user_change)

        # STATIC LAYOUT - No Paned Window
        main_content_frame = ttk.Frame(self.master)
        main_content_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)

        # Left panel - Directory tree (STATIC 220px width - optimized for professional-sized icons)
        left_frame = ttk.Frame(main_content_frame, width=220)
        left_frame.pack(side=tk.LEFT, fill=tk.Y, padx=(0, 10))
        left_frame.pack_propagate(False)  # Maintain fixed width

        ttk.Label(left_frame, text="Directories", font=("TkDefaultFont", 12, "bold")).pack(pady=(5, 10))

        self.directory_tree = ttk.Treeview(left_frame, show="tree")
        self.directory_tree.heading("#0", text="Directory Structure")

        # Apply consistent custom styling that works across all themes
        self.apply_custom_treeview_styling()

        self.directory_tree.pack(fill=tk.BOTH, expand=True, padx=8, pady=8)
        self.directory_tree.bind("<<TreeviewSelect>>", self.on_directory_select)
        self.directory_tree.bind("<Button-3>", self.on_directory_right_click)
        self.directory_tree.bind("<Button-1>", self.dismiss_context_menus)

        # Right panel - Content view (STATIC - fills remaining space)
        right_frame = ttk.Frame(main_content_frame)
        right_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        # Right panel header
        header_frame = ttk.Frame(right_frame)
        header_frame.pack(fill=tk.X, pady=5)

        self.current_path_label = ttk.Label(header_frame, text="Select a directory", font=("TkDefaultFont", 10, "bold"))
        self.current_path_label.pack(side=tk.LEFT)

        # Selection status label
        self.selection_status_label = ttk.Label(header_frame, text="", font=("TkDefaultFont", 9))
        self.selection_status_label.pack(side=tk.RIGHT, padx=10)

        # Content area - Icon view only
        self.content_frame = ttk.Frame(right_frame)
        self.content_frame.pack(fill=tk.BOTH, expand=True)

        # Icon view - use Canvas with scrollbar for grid layout
        self.icon_canvas_frame = ttk.Frame(self.content_frame)
        self.icon_canvas = tk.Canvas(self.icon_canvas_frame, highlightthickness=0)
        self.icon_scrollbar = ttk.Scrollbar(self.icon_canvas_frame, orient="vertical", command=self.icon_canvas.yview)
        self.icon_canvas.configure(yscrollcommand=self.icon_scrollbar.set)

        # Apply theme-appropriate background to canvas
        if TTKBOOTSTRAP_AVAILABLE:
            # Let ttkbootstrap handle canvas styling
            canvas_bg = self.style.colors.bg if hasattr(self.style, 'colors') else "#2e2e2e"
        else:
            canvas_bg = "#2e2e2e"
        
        self.icon_canvas.configure(bg=canvas_bg)

        self.icon_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.icon_canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        # Create a frame inside canvas for the grid
        self.icon_grid_frame = tk.Frame(self.icon_canvas, bg=canvas_bg)
        self.icon_canvas.create_window((0, 0), window=self.icon_grid_frame, anchor="nw")

        # Bind canvas resize
        self.icon_canvas.bind('<Configure>', self.on_canvas_configure)
        self.icon_grid_frame.bind('<Configure>', self.on_frame_configure)

        # Bind right-click to canvas for empty space context menu
        self.icon_canvas.bind("<Button-3>", self.on_empty_space_right_click)
        self.icon_grid_frame.bind("<Button-3>", self.on_empty_space_right_click)

        # Bind mouse wheel for scrolling
        self.icon_canvas.bind("<MouseWheel>", self.on_mousewheel)
        self.icon_canvas.bind("<Button-4>", self.on_mousewheel)
        self.icon_canvas.bind("<Button-5>", self.on_mousewheel)

        # Show icon view
        self.icon_canvas_frame.pack(fill=tk.BOTH, expand=True)

        # Variables for icon view
        self.icon_items = []
        self.selected_icon_item = None

        # Variables for drag selection
        self.selection_start_x = 0
        self.selection_start_y = 0
        self.selection_end_x = 0
        self.selection_end_y = 0
        self.is_selecting = False
        self.selected_items = []  # List of selected item names
        self.temp_intersecting_items = []  # Items currently intersecting with invisible selection area

        # Bind mouse events for drag selection
        self.icon_canvas.bind("<Button-1>", self.on_canvas_click)
        self.icon_canvas.bind("<B1-Motion>", self.on_canvas_drag)
        self.icon_canvas.bind("<ButtonRelease-1>", self.on_canvas_release)
        self.icon_grid_frame.bind("<Button-1>", self.on_canvas_click)
        self.icon_grid_frame.bind("<B1-Motion>", self.on_canvas_drag)
        self.icon_grid_frame.bind("<ButtonRelease-1>", self.on_canvas_release)

        # Bind click events to main window and frames to dismiss context menus
        self.master.bind("<Button-1>", self.dismiss_context_menus)
        left_frame.bind("<Button-1>", self.dismiss_context_menus)
        right_frame.bind("<Button-1>", self.dismiss_context_menus)

        # Create context menus
        print("Creating context menus...")
        self.create_context_menus()
        print("Context menus creation completed")

    def load_icons(self):
        def load_icon(path, size=(24, 24)):
            if not PIL_AVAILABLE:
                return None
            try:
                # Make path relative to script location
                script_dir = os.path.dirname(os.path.abspath(__file__))
                full_path = os.path.join(script_dir, path)
                
                # Check if file exists before trying to load
                if not os.path.exists(full_path):
                    return None
                    
                img = Image.open(full_path)
                img = img.resize(size, Image.LANCZOS)
                return ImageTk.PhotoImage(img)
            except Exception as e:
                # Silently fail for missing icons - don't print errors
                return None

        def create_text_icon(text, bg_color="white", fg_color="black", size=(24, 24)):
            """Create a simple text-based icon as fallback"""
            if not PIL_AVAILABLE:
                return None
            try:
                from PIL import Image, ImageDraw, ImageFont
                img = Image.new('RGBA', size, (0, 0, 0, 0))  # Transparent background
                draw = ImageDraw.Draw(img)
                
                # Try to get a better font for icons, fallback to default if not available
                try:
                    # Use proportional font size for professional appearance
                    font_size = max(12, size[0] // 3)  # Slightly smaller ratio for cleaner look
                    font = ImageFont.truetype("arial.ttf", font_size)
                except:
                    try:
                        # Try system default with appropriate size
                        font_size = max(12, size[0] // 3)
                        font = ImageFont.load_default()
                    except:
                        font = ImageFont.load_default()
                
                # Get text size and center it
                bbox = draw.textbbox((0, 0), text, font=font)
                text_width = bbox[2] - bbox[0]
                text_height = bbox[3] - bbox[1]
                x = (size[0] - text_width) // 2
                y = (size[1] - text_height) // 2
                
                draw.text((x, y), text, fill=fg_color, font=font)
                return ImageTk.PhotoImage(img)
            except Exception as e:
                print(f"Error creating text icon: {e}")
                return None

        ICON_SIZE = (40, 40)  # Professional size for directory tree - balanced between too small and too large
        LARGE_ICON_SIZE = (80, 80)  # Icons for main content area
        NAV_ICON_SIZE = (20, 20)  # Small icons for navigation buttons
        
        # Navigation icons - try to load from files first, then fallback to text
        self.back_icon = (load_icon("icons/icons8-reply-arrow-100.png", NAV_ICON_SIZE) or 
                         load_icon("icons/back.png", NAV_ICON_SIZE) or 
                         load_icon("icons/arrow-left.png", NAV_ICON_SIZE) or
                         create_text_icon("←", "transparent", "white", NAV_ICON_SIZE))
        
        self.forward_icon = (load_icon("icons/icons8-forward-arrow-100.png", NAV_ICON_SIZE) or 
                           load_icon("icons/forward.png", NAV_ICON_SIZE) or 
                           load_icon("icons/arrow-right.png", NAV_ICON_SIZE) or
                           create_text_icon("→", "transparent", "white", NAV_ICON_SIZE))
        
        # Try to load icons from the icons folder relative to script location
        self.folder_icon = load_icon("icons/icons8-folder-100.png", ICON_SIZE) or create_text_icon("📁", "transparent", "#FFA500")
        self.trash_icon = load_icon("icons/icons8-trash-100.png", (int(ICON_SIZE[0]*0.85), int(ICON_SIZE[1]*0.85))) or create_text_icon("🗑", "transparent", "#E74C3C")
        
        # Large icons for icon mode (create for all file types)
        self.folder_icon_large = load_icon("icons/icons8-folder-100.png", LARGE_ICON_SIZE) or create_text_icon("📁", "transparent", "#FFA500", LARGE_ICON_SIZE)
        self.trash_icon_large = load_icon("icons/icons8-trash-100.png", LARGE_ICON_SIZE) or create_text_icon("🗑", "transparent", "#E74C3C", LARGE_ICON_SIZE)
        
        # General file icons
        self.file_icon = load_icon("icons/icons8-file-50.png", ICON_SIZE) or create_text_icon("📄", "transparent", "lightblue")
        self.ro_icon = load_icon("icons/icons8-read-48.png", ICON_SIZE) or create_text_icon("RO", "transparent", "gray")
        self.rw_icon = load_icon("icons/icons8-pencil-48.png", ICON_SIZE) or create_text_icon("RW", "transparent", "lightgreen")
        
        # File type specific icons with text fallbacks (both small and large versions)
        self.txt_icon = load_icon("icons/icons8-txt-48.png", ICON_SIZE) or create_text_icon("TXT", "transparent", "lightblue")
        self.txt_icon_large = load_icon("icons/icons8-txt-48.png", LARGE_ICON_SIZE) or create_text_icon("TXT", "transparent", "lightblue", LARGE_ICON_SIZE)
        
        self.pdf_icon = load_icon("icons/icons8-pdf-100.png", ICON_SIZE) or create_text_icon("PDF", "transparent", "red")
        self.pdf_icon_large = load_icon("icons/icons8-pdf-100.png", LARGE_ICON_SIZE) or create_text_icon("PDF", "transparent", "red", LARGE_ICON_SIZE)
        
        self.doc_icon = load_icon("icons/icons8-doc-100.png", ICON_SIZE) or create_text_icon("DOC", "transparent", "blue")
        self.doc_icon_large = load_icon("icons/icons8-doc-100.png", LARGE_ICON_SIZE) or create_text_icon("DOC", "transparent", "blue", LARGE_ICON_SIZE)
        
        self.docx_icon = load_icon("icons/icons8-docx-100.png", ICON_SIZE) or create_text_icon("DOCX", "transparent", "blue")
        self.docx_icon_large = load_icon("icons/icons8-docx-100.png", LARGE_ICON_SIZE) or create_text_icon("DOCX", "transparent", "blue", LARGE_ICON_SIZE)
        
        self.xls_icon = load_icon("icons/icons8-xls-100.png", ICON_SIZE) or create_text_icon("XLS", "transparent", "green")
        self.xls_icon_large = load_icon("icons/icons8-xls-100.png", LARGE_ICON_SIZE) or create_text_icon("XLS", "transparent", "green", LARGE_ICON_SIZE)
        
        self.xlsx_icon = load_icon("icons/icons8-xlsx-48.png", ICON_SIZE) or create_text_icon("XLSX", "transparent", "green")
        self.xlsx_icon_large = load_icon("icons/icons8-xlsx-48.png", LARGE_ICON_SIZE) or create_text_icon("XLSX", "transparent", "green", LARGE_ICON_SIZE)
        
        self.ppt_icon = load_icon("icons/icons8-ppt-100.png", ICON_SIZE) or create_text_icon("PPT", "transparent", "orange")
        self.ppt_icon_large = load_icon("icons/icons8-ppt-100.png", LARGE_ICON_SIZE) or create_text_icon("PPT", "transparent", "orange", LARGE_ICON_SIZE)
        
        self.pptx_icon = load_icon("icons/icons8-pptx-48.png", ICON_SIZE) or create_text_icon("PPTX", "transparent", "orange")
        self.pptx_icon_large = load_icon("icons/icons8-pptx-48.png", LARGE_ICON_SIZE) or create_text_icon("PPTX", "transparent", "orange", LARGE_ICON_SIZE)
        
        self.jpg_icon = load_icon("icons/icons8-jpg-100.png", ICON_SIZE) or create_text_icon("JPG", "transparent", "purple")
        self.jpg_icon_large = load_icon("icons/icons8-jpg-100.png", LARGE_ICON_SIZE) or create_text_icon("JPG", "transparent", "purple", LARGE_ICON_SIZE)
        
        self.png_icon = load_icon("icons/icons8-png-100.png", ICON_SIZE) or create_text_icon("PNG", "transparent", "purple")
        self.png_icon_large = load_icon("icons/icons8-png-100.png", LARGE_ICON_SIZE) or create_text_icon("PNG", "transparent", "purple", LARGE_ICON_SIZE)
        
        self.gif_icon = load_icon("icons/icons8-gif-48.png", ICON_SIZE) or create_text_icon("GIF", "transparent", "purple")
        self.gif_icon_large = load_icon("icons/icons8-gif-48.png", LARGE_ICON_SIZE) or create_text_icon("GIF", "transparent", "purple", LARGE_ICON_SIZE)
        
        self.mp3_icon = load_icon("icons/icons8-mp3-48.png", ICON_SIZE) or create_text_icon("MP3", "transparent", "darkblue")
        self.mp3_icon_large = load_icon("icons/icons8-mp3-48.png", LARGE_ICON_SIZE) or create_text_icon("MP3", "transparent", "darkblue", LARGE_ICON_SIZE)
        
        self.mp4_icon = load_icon("icons/icons8-mp4-48.png", ICON_SIZE) or create_text_icon("MP4", "transparent", "darkred")
        self.mp4_icon_large = load_icon("icons/icons8-mp4-48.png", LARGE_ICON_SIZE) or create_text_icon("MP4", "transparent", "darkred", LARGE_ICON_SIZE)
        
        self.avi_icon = load_icon("icons/icons8-avi-48.png", ICON_SIZE) or create_text_icon("AVI", "transparent", "darkred")
        self.avi_icon_large = load_icon("icons/icons8-avi-48.png", LARGE_ICON_SIZE) or create_text_icon("AVI", "transparent", "darkred", LARGE_ICON_SIZE)
        
        self.zip_icon = load_icon("icons/icons8-zip-48.png", ICON_SIZE) or create_text_icon("ZIP", "transparent", "brown")
        self.zip_icon_large = load_icon("icons/icons8-zip-48.png", LARGE_ICON_SIZE) or create_text_icon("ZIP", "transparent", "brown", LARGE_ICON_SIZE)
        
        self.rar_icon = load_icon("icons/icons8-rar-48.png", ICON_SIZE) or create_text_icon("RAR", "transparent", "brown")
        self.rar_icon_large = load_icon("icons/icons8-rar-48.png", LARGE_ICON_SIZE) or create_text_icon("RAR", "transparent", "brown", LARGE_ICON_SIZE)
        
        self.py_icon = load_icon("icons/icons8-python-48.png", ICON_SIZE) or create_text_icon("PY", "transparent", "yellow")
        self.py_icon_large = load_icon("icons/icons8-python-48.png", LARGE_ICON_SIZE) or create_text_icon("PY", "transparent", "yellow", LARGE_ICON_SIZE)
        
        self.js_icon = load_icon("icons/icons8-javascript-48.png", ICON_SIZE) or create_text_icon("JS", "transparent", "yellow")
        self.js_icon_large = load_icon("icons/icons8-javascript-48.png", LARGE_ICON_SIZE) or create_text_icon("JS", "transparent", "yellow", LARGE_ICON_SIZE)
        
        self.html_icon = load_icon("icons/icons8-html-48.png", ICON_SIZE) or create_text_icon("HTML", "transparent", "orange")
        self.html_icon_large = load_icon("icons/icons8-html-48.png", LARGE_ICON_SIZE) or create_text_icon("HTML", "transparent", "orange", LARGE_ICON_SIZE)
        
        self.css_icon = load_icon("icons/icons8-css-48.png", ICON_SIZE) or create_text_icon("CSS", "transparent", "blue")
        self.css_icon_large = load_icon("icons/icons8-css-48.png", LARGE_ICON_SIZE) or create_text_icon("CSS", "transparent", "blue", LARGE_ICON_SIZE)
        
        self.java_icon = load_icon("icons/icons8-java-48.png", ICON_SIZE) or create_text_icon("JAVA", "transparent", "red")
        self.java_icon_large = load_icon("icons/icons8-java-48.png", LARGE_ICON_SIZE) or create_text_icon("JAVA", "transparent", "red", LARGE_ICON_SIZE)
        
        self.cpp_icon = load_icon("icons/icons8-cpp-48.png", ICON_SIZE) or create_text_icon("C++", "transparent", "blue")
        self.cpp_icon_large = load_icon("icons/icons8-cpp-48.png", LARGE_ICON_SIZE) or create_text_icon("C++", "transparent", "blue", LARGE_ICON_SIZE)
        
        self.exe_icon = load_icon("icons/icons8-exe-48.png", ICON_SIZE) or create_text_icon("EXE", "transparent", "black")
        self.exe_icon_large = load_icon("icons/icons8-exe-48.png", LARGE_ICON_SIZE) or create_text_icon("EXE", "transparent", "black", LARGE_ICON_SIZE)
        
        # User role icons
        self.user_icon = load_icon("icons/icons8-admin-100.png", (24, 24)) or create_text_icon("👤", "transparent", "lightblue")
        self.admin_icon = load_icon("icons/icons8-user-100.png", (24, 24)) or create_text_icon("🛡", "transparent", "red")

    def get_file_icon(self, filename, permissions, large=False):
        """Get appropriate icon based on file extension and permissions"""
        if not filename or '.' not in filename:
            # No extension, use default based on permissions
            return self.ro_icon if permissions == 0 else self.rw_icon
        
        extension = filename.lower().split('.')[-1]
        
        # File type specific icons
        if large:
            icon_map = {
                'txt': self.txt_icon_large,
                'pdf': self.pdf_icon_large,
                'doc': self.doc_icon_large,
                'docx': self.docx_icon_large,
                'xls': self.xls_icon_large,
                'xlsx': self.xlsx_icon_large,
                'ppt': self.ppt_icon_large,
                'pptx': self.pptx_icon_large,
                'jpg': self.jpg_icon_large,
                'jpeg': self.jpg_icon_large,
                'png': self.png_icon_large,
                'gif': self.gif_icon_large,
                'mp3': self.mp3_icon_large,
                'wav': self.mp3_icon_large,
                'mp4': self.mp4_icon_large,
                'mkv': self.mp4_icon_large,
                'avi': self.avi_icon_large,
                'zip': self.zip_icon_large,
                'rar': self.rar_icon_large,
                '7z': self.zip_icon_large,
                'py': self.py_icon_large,
                'js': self.js_icon_large,
                'html': self.html_icon_large,
                'htm': self.html_icon_large,
                'css': self.css_icon_large,
                'java': self.java_icon_large,
                'cpp': self.cpp_icon_large,
                'c': self.cpp_icon_large,
                'exe': self.exe_icon_large,
                'msi': self.exe_icon_large
            }
        else:
            icon_map = {
                'txt': self.txt_icon,
                'pdf': self.pdf_icon,
                'doc': self.doc_icon,
                'docx': self.docx_icon,
                'xls': self.xls_icon,
                'xlsx': self.xlsx_icon,
                'ppt': self.ppt_icon,
                'pptx': self.pptx_icon,
                'jpg': self.jpg_icon,
                'jpeg': self.jpg_icon,
                'png': self.png_icon,
                'gif': self.gif_icon,
                'mp3': self.mp3_icon,
                'wav': self.mp3_icon,
                'mp4': self.mp4_icon,
                'mkv': self.mp4_icon,
                'avi': self.avi_icon,
                'zip': self.zip_icon,
                'rar': self.rar_icon,
                '7z': self.zip_icon,
                'py': self.py_icon,
                'js': self.js_icon,
                'html': self.html_icon,
                'htm': self.html_icon,
                'css': self.css_icon,
                'java': self.java_icon,
                'cpp': self.cpp_icon,
                'c': self.cpp_icon,
                'exe': self.exe_icon,
                'msi': self.exe_icon
            }
        
        # Get specific icon or fallback to permission-based icon
        specific_icon = icon_map.get(extension)
        if specific_icon:
            return specific_icon
        else:
            # Fallback to permission-based icon
            return self.ro_icon if permissions == 0 else self.rw_icon

    def get_folder_icon(self, folder_name, large=False):
        """Get appropriate icon for folders"""
        if folder_name == "Trash":
            return self.trash_icon_large if large else self.trash_icon
        else:
            return self.folder_icon_large if large else self.folder_icon

    def create_icon_item(self, name, icon, is_directory=False):
        """Create an icon item for the grid view with transparent background and precise highlighting"""
        # Get current canvas background color for transparency
        canvas_bg = self.icon_canvas.cget('bg')
        
        # Create main frame with transparent background
        frame = tk.Frame(self.icon_grid_frame, bg=canvas_bg, cursor="hand2", 
                        width=120, height=140, relief="flat", bd=0)
        frame.pack_propagate(False)  # Don't shrink to fit content
        
        # Icon label with transparent background
        if icon:
            icon_label = tk.Label(frame, image=icon, bg=canvas_bg, bd=0, relief="flat")
        else:
            icon_label = tk.Label(frame, text="📁" if is_directory else "📄", 
                                font=("Arial", 56), bg=canvas_bg, fg="white", bd=0, relief="flat")
        icon_label.pack(pady=(12, 8))
        
        # Name label with transparent background and limited height
        name_label = tk.Label(frame, text=name, bg=canvas_bg, fg="white", 
                            font=("Arial", 11), wraplength=110, justify="center", 
                            bd=0, relief="flat")
        name_label.pack(pady=(0, 12), fill=tk.X)
        
        # Store original background colors for highlighting
        frame.original_bg = canvas_bg
        icon_label.original_bg = canvas_bg
        name_label.original_bg = canvas_bg
        
        # Bind events to both frame and labels - prevent propagation to canvas
        def on_double_click(e):
            self.on_icon_double_click(name)
            return "break"
            
        def on_right_click(e):
            self.on_icon_right_click(e, name)
            return "break"
            
        def on_single_click(e):
            self.on_icon_single_click(name)
            return "break"
        
        for widget in [frame, icon_label, name_label]:
            widget.bind("<Double-Button-1>", on_double_click)
            widget.bind("<Button-3>", on_right_click)
            widget.bind("<Button-1>", on_single_click)
        
        return frame

    def highlight_item(self, item_frame, highlight):
        """Highlight or unhighlight an item frame with precise selection area"""
        if highlight:
            # Modern selection effect - subtle highlight that fits content
            selection_color = "#0078d4"  # Windows-style blue selection
            
            # Apply highlighting only to the content areas
            for child in item_frame.winfo_children():
                if isinstance(child, tk.Label):
                    # Create a subtle background highlight for text
                    child.config(bg=selection_color, fg="white")
            
            # Add a subtle border to the frame
            item_frame.config(bg=selection_color, relief="solid", bd=1)
            
        else:
            # Restore original transparent appearance
            canvas_bg = self.icon_canvas.cget('bg')
            
            # Restore all child widgets to transparent background
            for child in item_frame.winfo_children():
                if isinstance(child, tk.Label):
                    child.config(bg=canvas_bg, fg="white")
            
            # Restore frame to transparent
            item_frame.config(bg=canvas_bg, relief="flat", bd=0)

    def apply_dark_theme(self):
        """Apply dark theme styling"""
        if not TTKBOOTSTRAP_AVAILABLE:
            # Manual dark theme for standard ttk
            style = ttk.Style()
            style.theme_use("clam")
            
            # Configure dark colors
            style.configure("TFrame", background="#2e2e2e")
            style.configure("TLabel", background="#2e2e2e", foreground="white")
            style.configure("TButton", background="#404040", foreground="white")
            style.configure("TEntry", background="#404040", foreground="white", fieldbackground="#404040")
            style.configure("TCombobox", background="#404040", foreground="white", fieldbackground="#404040")
            
            # Configure treeview
            style.configure("Treeview", 
                          background="#2e2e2e", 
                          foreground="white", 
                          fieldbackground="#2e2e2e")
            style.configure("Treeview.Heading", 
                          background="#1e1e1e", 
                          foreground="white")

    # Update the file opening method to use OS applications
    def open_file_with_application(self, file):
        """Open a file with OS default application instead of custom viewers"""
        if not file:
            return
        
        print(f"Opening file: {file.name} with OS default application")
        
        # Use the new OS application opening function
        success = open_file_with_os_application(file)
        
        if not success:
            # If OS opening failed, show the file details dialog as fallback
            print(f"OS application opening failed, showing file details instead")
            self.show_file_details_dialog(file)

    def show_file_details_dialog(self, file):
        """Show file details in a dialog as fallback when OS application fails"""
        content = file.content or "[Empty file]"
        file_info = f"""File: {file.name}
Size: {file.get_size_display()}
Allocation: {file.allocation}
Permissions: {'Read-Only' if file.permissions == 0 else 'Read-Write'}
Last Modified: {file.timestamp}

--- Content Preview ---
{content[:500]}{'...' if len(content) > 500 else ''}"""
        
        # Create a custom dialog with scrollable text
        details_window = tk.Toplevel(self.master)
        details_window.title(f"File Details - {file.name}")
        details_window.geometry("600x500")
        details_window.configure(bg=self.colors.get('bg', '#f0f0f0'))
        
        # Create text widget with scrollbar
        text_frame = tk.Frame(details_window, bg=self.colors.get('bg', '#f0f0f0'))
        text_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        scrollbar = tk.Scrollbar(text_frame)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        text_widget = tk.Text(text_frame, 
                            yscrollcommand=scrollbar.set,
                            bg=self.colors.get('editor_bg', '#ffffff'),
                            fg=self.colors.get('editor_fg', '#000000'),
                            font=self.get_safe_font('mono'),
                            wrap=tk.WORD)
        text_widget.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        
        scrollbar.config(command=text_widget.yview)
        
        text_widget.insert(tk.END, file_info)
        text_widget.config(state=tk.DISABLED)  # Make read-only
        
        # Close button
        close_btn = tk.Button(details_window, text="Close", 
                            command=details_window.destroy,
                            font=self.get_safe_font('default'))
        close_btn.pack(pady=10)

    # Rest of the methods remain the same as the original code...
    # [Include all the remaining methods from the original code]

    def update_user_dropdown(self):
        """Update the user dropdown with current users and Add User option"""
        # Create list of user options
        user_options = []
        for user in user_list:
            role_display = "ADMIN" if user["role"] == UserRole.ADMIN else "USER"
            user_options.append(f"{user['username']} ({role_display})")

        # Add the "Add User..." option at the end
        user_options.append("➕ Add User...")

        # Update dropdown values
        self.user_dropdown['values'] = user_options
    
    def on_user_change(self, event=None):
        """Handle user dropdown selection change"""
        selected = self.user_var.get()

        if selected == "➕ Add User...":
            # Show add user dialog
            self.show_add_user_dialog()
        else:
            # Parse the selected user
            # Format: "username (ROLE)"
            if " (" in selected and selected.endswith(")"):
                username = selected.split(" (")[0]
                role_part = selected.split(" (")[1].rstrip(")")

                # Find the user in user_list
                for user in user_list:
                    if user["username"] == username:
                        current_user["username"] = user["username"]
                        current_user["role"] = user["role"]
                        break
                    
                self.update_role_display()
                print(f"Switched to: {current_user['username']} ({current_user['role']})")

    def show_add_user_dialog(self):
        """Show a nice dialog to add a new user"""
        # Create custom dialog window
        dialog = tk.Toplevel(self.master)
        dialog.title("Add New User")
        dialog.geometry("400x250")
        dialog.configure(bg=self.colors.get('bg', '#f0f0f0'))
        dialog.transient(self.master)
        dialog.resizable(False, False)
        dialog.grab_set()  # Make it modal

        # Center the dialog
        dialog.geometry("+%d+%d" % (self.master.winfo_rootx() + 150, 
                                  self.master.winfo_rooty() + 100))

        # Dialog content
        # Header
        header_frame = tk.Frame(dialog, bg=self.colors.get('bg', '#f0f0f0'))
        header_frame.pack(fill=tk.X, padx=20, pady=20)

        # Icon and title
        icon_label = tk.Label(header_frame, 
                             image=self.user_icon if self.user_icon else None,
                             bg=self.colors.get('bg', '#f0f0f0'))
        icon_label.pack(side=tk.LEFT, padx=(0, 10))

        title_label = tk.Label(header_frame, 
                              text="Create New User", 
                              font=self.get_safe_font('large'),
                              bg=self.colors.get('bg', '#f0f0f0'),
                              fg=self.colors.get('fg', '#000000'))
        title_label.pack(side=tk.LEFT)

        # Input section
        input_frame = tk.Frame(dialog, bg=self.colors.get('bg', '#f0f0f0'))
        input_frame.pack(fill=tk.X, padx=20, pady=10)

        tk.Label(input_frame, 
                 text="Enter username:", 
                 font=self.get_safe_font('default'),
                 bg=self.colors.get('bg', '#f0f0f0'),
                 fg=self.colors.get('fg', '#000000')).pack(anchor="w", pady=(0, 5))

        username_entry = tk.Entry(input_frame, 
                                 font=self.get_safe_font('default'),
                                 width=30)
        username_entry.pack(fill=tk.X, pady=(0, 10))
        username_entry.focus()

        # Role selection
        tk.Label(input_frame, 
                 text="Select role:", 
                 font=self.get_safe_font('default'),
                 bg=self.colors.get('bg', '#f0f0f0'),
                 fg=self.colors.get('fg', '#000000')).pack(anchor="w", pady=(10, 5))

        role_var = tk.StringVar(value="USER")
        role_frame = tk.Frame(input_frame, bg=self.colors.get('bg', '#f0f0f0'))
        role_frame.pack(fill=tk.X)

        user_radio = tk.Radiobutton(role_frame, text="User (Standard access)", 
                                   variable=role_var, value="USER",
                                   font=self.get_safe_font('default'),
                                   bg=self.colors.get('bg', '#f0f0f0'),
                                   fg=self.colors.get('fg', '#000000'),
                                   selectcolor=self.colors.get('bg', '#f0f0f0'))
        user_radio.pack(anchor="w")

        admin_radio = tk.Radiobutton(role_frame, text="Admin (Full access)", 
                                    variable=role_var, value="ADMIN",
                                    font=self.get_safe_font('default'),
                                    bg=self.colors.get('bg', '#f0f0f0'),
                                    fg=self.colors.get('fg', '#000000'),
                                    selectcolor=self.colors.get('bg', '#f0f0f0'))
        admin_radio.pack(anchor="w")

        # Buttons
        button_frame = tk.Frame(dialog, bg=self.colors.get('bg', '#f0f0f0'))
        button_frame.pack(fill=tk.X, padx=20, pady=20)

        def create_user():
            username = username_entry.get().strip()
            role = role_var.get()

            if not username:
                messagebox.showerror("Error", "Please enter a username.", parent=dialog)
                return

            if len(username) < 2:
                messagebox.showerror("Error", "Username must be at least 2 characters long.", parent=dialog)
                return

            if not username.replace('_', '').replace('-', '').isalnum():
                messagebox.showerror("Error", "Username can only contain letters, numbers, hyphens, and underscores.", parent=dialog)
                return

            # Check if username already exists
            if any(user["username"].lower() == username.lower() for user in user_list):
                messagebox.showerror("Error", f"Username '{username}' already exists.", parent=dialog)
                return

            # Limit number of users
            if len(user_list) >= 10:
                messagebox.showerror("Error", "Maximum number of users (10) reached.", parent=dialog)
                return

            # Create new user
            new_role = UserRole.ADMIN if role == "ADMIN" else UserRole.USER
            new_user = {"username": username, "role": new_role}
            user_list.append(new_user)

            # Update dropdown
            self.update_user_dropdown()

            # Switch to new user
            current_user["username"] = username
            current_user["role"] = new_role
            self.user_var.set(f"{username} ({'ADMIN' if new_role == UserRole.ADMIN else 'USER'})")
            self.update_role_display()

            print(f"Created new user: {username} ({new_role})")
            dialog.destroy()

        def cancel_dialog():
            # Reset dropdown to current user
            role_display = "ADMIN" if current_user["role"] == UserRole.ADMIN else "USER"
            self.user_var.set(f"{current_user['username']} ({role_display})")
            dialog.destroy()

        # Create User button
        create_btn = tk.Button(button_frame, text="Create User", 
                              command=create_user,
                              font=self.get_safe_font('default'),
                              bg="#4a90e2", fg="white",
                              padx=20, pady=5)
        create_btn.pack(side=tk.RIGHT, padx=(10, 0))

        # Cancel button  
        cancel_btn = tk.Button(button_frame, text="Cancel", 
                              command=cancel_dialog,
                              font=self.get_safe_font('default'),
                              padx=20, pady=5)
        cancel_btn.pack(side=tk.RIGHT)

        # Bind Enter key to create user
        dialog.bind('<Return>', lambda e: create_user())
        dialog.bind('<Escape>', lambda e: cancel_dialog())

        # Handle window close
        dialog.protocol("WM_DELETE_WINDOW", cancel_dialog)

    def create_context_menus(self):
        # Directory context menu
        self.dir_context_menu = tk.Menu(self.master, tearoff=0)
        self.dir_context_menu.add_command(label="Open", command=self.open_directory)
        self.dir_context_menu.add_command(label="Rename", command=self.rename_directory)
        self.dir_context_menu.add_separator()
        self.dir_context_menu.add_command(label="Cut (Ctrl+X)", command=self.cut_selected)
        self.dir_context_menu.add_command(label="Copy (Ctrl+C)", command=self.copy_selected)
        self.dir_context_menu.add_separator()
        self.dir_context_menu.add_command(label="Create File", command=self.create_file_in_selected)
        self.dir_context_menu.add_command(label="Create Directory", command=self.create_directory_in_selected)
        self.dir_context_menu.add_separator()
        self.dir_context_menu.add_command(label="Delete", command=self.delete_selected_directory)
        self.dir_context_menu.add_separator()
        self.dir_context_menu.add_command(label="Refresh", command=self.refresh_all)

        # File context menu (normal files)
        self.file_context_menu = tk.Menu(self.master, tearoff=0)
        self.file_context_menu.add_command(label="Open", command=self.open_selected_file_with_app)
        self.file_context_menu.add_command(label="View Details", command=self.read_selected_file)
        self.file_context_menu.add_command(label="Rename", command=self.rename_file)
        self.file_context_menu.add_separator()
        self.file_context_menu.add_command(label="Cut (Ctrl+X)", command=self.cut_selected)
        self.file_context_menu.add_command(label="Copy (Ctrl+C)", command=self.copy_selected)
        self.file_context_menu.add_separator()
        self.file_context_menu.add_command(label="Delete", command=self.delete_selected_file)
        self.file_context_menu.add_separator()
        self.file_context_menu.add_command(label="Refresh", command=self.refresh_content)

        # Trash file context menu (files in trash)
        self.trash_file_context_menu = tk.Menu(self.master, tearoff=0)
        self.trash_file_context_menu.add_command(label="Open", command=self.open_selected_file_with_app)
        self.trash_file_context_menu.add_command(label="View Details", command=self.read_selected_file)
        self.trash_file_context_menu.add_separator()
        self.trash_file_context_menu.add_command(label="Restore from Trash", command=self.restore_selected_file)
        self.trash_file_context_menu.add_command(label="Delete from Trash", command=self.delete_permanently_selected_file)

        # Trash directory context menu (directories in trash)
        self.trash_dir_context_menu = tk.Menu(self.master, tearoff=0)
        self.trash_dir_context_menu.add_command(label="Open", command=self.open_directory)
        self.trash_dir_context_menu.add_separator()
        self.trash_dir_context_menu.add_command(label="Restore from Trash", command=self.restore_selected_directory)
        self.trash_dir_context_menu.add_command(label="Delete from Trash", command=self.delete_permanently_selected_directory)

        # Empty space context menu (for right panel)
        self.empty_context_menu = tk.Menu(self.master, tearoff=0)
        self.empty_context_menu.add_command(label="Create File", command=self.create_file_in_current)
        self.empty_context_menu.add_command(label="Create Directory", command=self.create_directory_in_current)
        self.empty_context_menu.add_separator()
        self.empty_context_menu.add_command(label="Paste (Ctrl+V)", command=self.paste_to_current)
        self.empty_context_menu.add_separator()
        self.empty_context_menu.add_command(label="Refresh", command=self.refresh_content)

        # Trash empty space context menu - SIMPLIFIED FOR TRASH ONLY
        self.trash_empty_context_menu = tk.Menu(self.master, tearoff=0)
        self.trash_empty_context_menu.add_command(label="Empty Trash", command=self.empty_trash)
        self.trash_empty_context_menu.add_separator()
        self.trash_empty_context_menu.add_command(label="Refresh", command=self.refresh_content)

        # Mixed selection context menus (CREATE THEM IMMEDIATELY)
        self.mixed_context_menu = tk.Menu(self.master, tearoff=0)
        self.mixed_context_menu.add_command(label="Cut Selected Items (Ctrl+X)", command=self.cut_selected)
        self.mixed_context_menu.add_command(label="Copy Selected Items (Ctrl+C)", command=self.copy_selected)
        self.mixed_context_menu.add_separator()
        self.mixed_context_menu.add_command(label="Delete Selected Items", command=self.delete_mixed_selection_to_trash)
        self.mixed_context_menu.add_separator()
        self.mixed_context_menu.add_command(label="Refresh", command=self.refresh_content)

        self.trash_mixed_context_menu = tk.Menu(self.master, tearoff=0)
        self.trash_mixed_context_menu.add_command(label="Restore Selected Items", command=self.restore_mixed_selection)
        self.trash_mixed_context_menu.add_command(label="Delete Selected Items Permanently", command=self.delete_permanently_mixed_selection)
        self.trash_mixed_context_menu.add_separator()
        self.trash_mixed_context_menu.add_command(label="Refresh", command=self.refresh_content)

    # [Continue with all the rest of the methods from the original code - the remaining methods are unchanged]
    # I'll include the key methods here for context:

    def dismiss_context_menus(self, event=None):
        """Dismiss all context menus when clicking elsewhere"""
        try:
            self.dir_context_menu.unpost()
            self.file_context_menu.unpost()
            self.trash_file_context_menu.unpost()
            self.trash_dir_context_menu.unpost()
            self.empty_context_menu.unpost()
            self.trash_empty_context_menu.unpost()
            self.trash_mixed_context_menu.unpost()
            self.mixed_context_menu.unpost()

            if hasattr(self, 'dynamic_dir_context_menu'):
                self.dynamic_dir_context_menu.unpost()
        except:
            pass

    def open_selected_file_with_app(self):
        """Open the selected file with its appropriate OS application"""
        if not self.selected_item or not self.current_directory:
            return
        
        for file in self.current_directory.files:
            if file.name == self.selected_item:
                print(f"Opening file: {file.name} with OS default application")
                self.open_file_with_application(file)
                return
        messagebox.showerror("Error", "File not found.")

    def read_selected_file(self):
        if not self.selected_item or not self.current_directory:
            return
        
        for file in self.current_directory.files:
            if file.name == self.selected_item:
                self.show_file_details_dialog(file)
                return
        messagebox.showerror("Error", "File not found.")

    def on_icon_double_click(self, item_name):
        """Handle double-click on icon items - opens directories and files with OS applications"""
        # Clear any active selection first
        self.clear_selection()

        # Check if it's a directory by looking for it in subdirectories
        for subdir in self.current_directory.subdirectories:
            if subdir.name == item_name:
                # Navigate to subdirectory
                self.navigate_to_directory(subdir)
                return

        # If not a directory, it's a file - open with OS default application
        for file in self.current_directory.files:
            if file.name == item_name:
                self.open_file_with_application(file)
                return

        # If neither found, show error
        print(f"Item '{item_name}' not found in current directory")

    # [Include all the remaining methods from the original code - they remain unchanged]
    
    def setup_os_specific_config(self):
        """Setup OS-specific configurations"""
        if self.os_type == 'windows':
            self.setup_windows_config()
        elif self.os_type == 'darwin':  # macOS
            self.setup_macos_config()
        else:  # Linux/Unix
            self.setup_linux_config()
    
    def setup_windows_config(self):
        """Windows-specific configuration"""
        self.fonts = {
            'default': ('Segoe UI', 11),
            'mono': ('Consolas', 11),
            'large': ('Segoe UI', 14),
            'small': ('Segoe UI', 9)
        }
        self.colors = {
            'bg': '#f0f0f0',
            'fg': '#000000',
            'editor_bg': '#ffffff',
            'editor_fg': '#000000',
            'toolbar_bg': '#e1e1e1',
            'dark_bg': '#2d2d30',
            'dark_fg': '#ffffff'
        }
        self.app_style = 'windows'
    
    def setup_macos_config(self):
        """macOS-specific configuration"""
        self.fonts = {
            'default': ('SF Pro Display', 11),
            'mono': ('SF Mono', 11),
            'large': ('SF Pro Display', 14),
            'small': ('SF Pro Display', 9)
        }
        self.colors = {
            'bg': '#ececec',
            'fg': '#000000',
            'editor_bg': '#ffffff',
            'editor_fg': '#000000',
            'toolbar_bg': '#e8e8e8',
            'dark_bg': '#2c2c2c',
            'dark_fg': '#ffffff'
        }
        self.app_style = 'macos'

    def setup_linux_config(self):
        """Linux/Ubuntu-specific configuration"""
        self.fonts = {
            'default': ('Ubuntu', 11),
            'mono': ('Ubuntu Mono', 11),
            'large': ('Ubuntu', 14),
            'small': ('Ubuntu', 9)
        }
        self.colors = {
            'bg': '#f5f5f5',
            'fg': '#2e3436',
            'editor_bg': '#ffffff',
            'editor_fg': '#2e3436',
            'toolbar_bg': '#e8e8e8',
            'dark_bg': '#2e2e2e',
            'dark_fg': '#ffffff'
        }
        self.app_style = 'linux'

    def get_safe_font(self, font_type='default'):
        """Get a safe font that works across platforms"""
        try:
            return self.fonts[font_type]
        except:
            # Fallback fonts if the preferred ones aren't available
            fallback_fonts = {
                'windows': {
                    'default': ('Arial', 11),
                    'mono': ('Courier New', 11),
                    'large': ('Arial', 14),
                    'small': ('Arial', 9)
                },
                'darwin': {
                    'default': ('Helvetica', 11),
                    'mono': ('Monaco', 11),
                    'large': ('Helvetica', 14),
                    'small': ('Helvetica', 9)
                },
                'linux': {
                    'default': ('DejaVu Sans', 11),
                    'mono': ('DejaVu Sans Mono', 11),
                    'large': ('DejaVu Sans', 14),
                    'small': ('DejaVu Sans', 9)
                }
            }
            
            try:
                return fallback_fonts[self.os_type][font_type]
            except:
                # Ultimate fallback
                sizes = {'default': 11, 'mono': 11, 'large': 14, 'small': 9}
                return ('TkDefaultFont', sizes.get(font_type, 11))

    def on_empty_space_right_click(self, event):
        """Handle right-click on empty space - different menus for trash vs normal directories"""
        self.dismiss_context_menus()

        # Update selection status
        self.update_selection_status()

        # Check if we're in the trash directory
        if self.current_directory and self.current_directory.name == "Trash":
            # Show simplified trash context menu
            self.trash_empty_context_menu.post(event.x_root, event.y_root)
        else:
            # Show normal context menu
            # Update the paste option based on clipboard state
            self.empty_context_menu.entryconfig("Paste (Ctrl+V)", 
                                              state=tk.NORMAL if can_paste_here(self.current_directory) else tk.DISABLED)
            self.empty_context_menu.post(event.x_root, event.y_root)

    def on_mousewheel(self, event):
        """Handle mouse wheel scrolling in icon view"""
        if hasattr(event, 'delta'):
            # Windows
            self.icon_canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")
        elif event.num == 4:
            # Linux scroll up
            self.icon_canvas.yview_scroll(-1, "units")
        elif event.num == 5:
            # Linux scroll down
            self.icon_canvas.yview_scroll(1, "units")

    def on_canvas_configure(self, event):
        """Handle canvas resize"""
        self.icon_canvas.configure(scrollregion=self.icon_canvas.bbox("all"))
        # Update grid layout when canvas size changes
        self.master.after_idle(self.update_icon_grid)

    def on_frame_configure(self, event):
        """Handle frame resize"""
        self.icon_canvas.configure(scrollregion=self.icon_canvas.bbox("all"))

    def update_icon_grid(self):
        """Update the icon grid layout to fit canvas width"""
        if not hasattr(self, 'icon_items') or not self.icon_items:
            return
            
        canvas_width = self.icon_canvas.winfo_width()
        if canvas_width <= 1:
            return
            
        # Calculate how many icons can fit horizontally (increased spacing for larger icons)
        icon_width = 140  # Increased from 120 to 140 for larger icons
        cols = max(1, canvas_width // icon_width)
        
        # Rearrange icons in grid with more spacing
        for i, item in enumerate(self.icon_items):
            row = i // cols
            col = i % cols
            item.grid(row=row, column=col, padx=25, pady=25, sticky="n")  # Increased padding from 20 to 25

    def on_canvas_click(self, event):
        """Handle mouse click on canvas - start invisible drag selection"""
        # Clear previous selections
        self.clear_selection()
        
        # Get canvas coordinates
        canvas_x = self.icon_canvas.canvasx(event.x)
        canvas_y = self.icon_canvas.canvasy(event.y)
        
        self.selection_start_x = canvas_x
        self.selection_start_y = canvas_y
        self.selection_end_x = canvas_x
        self.selection_end_y = canvas_y
        self.is_selecting = True
        self.temp_intersecting_items = []  # Initialize temporary intersecting items
        
        # Dismiss context menus
        self.dismiss_context_menus()

    def on_canvas_drag(self, event):
        """Handle mouse drag on canvas - update invisible selection area"""
        if not self.is_selecting:
            return
            
        # Get canvas coordinates
        canvas_x = self.icon_canvas.canvasx(event.x)
        canvas_y = self.icon_canvas.canvasy(event.y)
        
        self.selection_end_x = canvas_x
        self.selection_end_y = canvas_y
        
        # Update invisible selection area (this will apply fade effects to icons)
        self.update_selection_rectangle()

    def on_canvas_release(self, event):
        """Handle mouse release on canvas - finalize selection"""
        if not self.is_selecting:
            return
            
        self.is_selecting = False
        
        # Get canvas coordinates
        canvas_x = self.icon_canvas.canvasx(event.x)
        canvas_y = self.icon_canvas.canvasy(event.y)
        
        self.selection_end_x = canvas_x
        self.selection_end_y = canvas_y
        
        # Finalize selection (no rectangle cleanup needed since we don't draw one)
        self.finalize_selection()

    def update_selection_rectangle(self):
        """Update the invisible selection area and apply real-time fade effects to icons"""
        # Don't draw any visible rectangle - just track the selection area invisibly
        # and apply highlighting to intersecting items
        
        # Calculate rectangle coordinates (invisible)
        x1 = min(self.selection_start_x, self.selection_end_x)
        y1 = min(self.selection_start_y, self.selection_end_y)
        x2 = max(self.selection_start_x, self.selection_end_x)
        y2 = max(self.selection_start_y, self.selection_end_y)
        
        # Only apply effects if the area is meaningful size
        if abs(x2 - x1) > 5 and abs(y2 - y1) > 5:
            # Apply real-time fade effect to intersecting items (no visible rectangle)
            self.apply_realtime_selection_fade(x1, y1, x2, y2)

    def apply_realtime_selection_fade(self, x1, y1, x2, y2):
        """Apply fade effect to items currently intersecting with selection rectangle"""
        # First, reset all items to normal state
        for item_frame in self.icon_items:
            self.highlight_item(item_frame, False)
        
        # Then apply prominent highlight to intersecting items
        currently_intersecting = []
        
        for i, item_frame in enumerate(self.icon_items):
            # Get item position on canvas
            item_x = item_frame.winfo_x()
            item_y = item_frame.winfo_y()
            item_width = item_frame.winfo_width()
            item_height = item_frame.winfo_height()
            
            # Check if item intersects with selection rectangle
            if (item_x < x2 and item_x + item_width > x1 and 
                item_y < y2 and item_y + item_height > y1):
                
                # Apply prominent highlight effect immediately
                self.highlight_item(item_frame, True)
                
                # Get item name for tracking
                if i < len(self.current_directory.subdirectories):
                    item_name = self.current_directory.subdirectories[i].name
                else:
                    file_index = i - len(self.current_directory.subdirectories)
                    if file_index < len(self.current_directory.files):
                        item_name = self.current_directory.files[file_index].name
                    else:
                        continue
                
                currently_intersecting.append(item_name)
        
        # Store temporarily intersecting items
        self.temp_intersecting_items = currently_intersecting
        
        # Update selection status in real-time
        if currently_intersecting:
            count = len(currently_intersecting)
            if count == 1:
                self.selection_status_label.config(text="1 item selected")
            else:
                self.selection_status_label.config(text=f"{count} items selected")
        else:
            self.selection_status_label.config(text="")

    def finalize_selection(self):
        """Finalize the selection using items that were already highlighted during drag"""
        # Use the items that were being highlighted during the drag
        self.selected_items = self.temp_intersecting_items.copy() if hasattr(self, 'temp_intersecting_items') else []
        
        # Update selected_item for compatibility with single-selection code
        if len(self.selected_items) == 1:
            self.selected_item = self.selected_items[0]
            # Determine if it's a file or directory
            self.selected_item_type = "directory" if any(subdir.name == self.selected_item for subdir in self.current_directory.subdirectories) else "file"
        elif len(self.selected_items) > 1:
            self.selected_item = None  # Multiple selection
            self.selected_item_type = None
        else:
            self.selected_item = None
            self.selected_item_type = None
        
        # Update selection status
        self.update_selection_status()
        
        # Clear temporary intersecting items
        self.temp_intersecting_items = []

    def clear_selection(self):
        """Clear all selections and remove highlighting"""
        # Clear visual highlights
        for item_frame in self.icon_items:
            self.highlight_item(item_frame, False)
        
        # Clear selection state
        self.selected_items = []
        self.selected_item = None
        self.selected_item_type = None
        self.is_selecting = False
        self.temp_intersecting_items = []  # Clear temporary intersecting items
        
        # Update selection status
        self.update_selection_status()

    def update_selection_status(self):
        """Update the selection status label"""
        if not self.selected_items:
            self.selection_status_label.config(text="")
        elif len(self.selected_items) == 1:
            self.selection_status_label.config(text=f"1 item selected")
        else:
            self.selection_status_label.config(text=f"{len(self.selected_items)} items selected")

    def on_icon_single_click(self, item_name):
        """Handle single-click on icon items to select them with prominent highlight"""
        # Clear previous selections first
        self.clear_selection()
        
        # Set the single selection
        self.selected_item = item_name
        self.selected_items = [item_name]
        
        # Determine if it's a file or directory
        self.selected_item_type = "directory" if any(subdir.name == item_name for subdir in self.current_directory.subdirectories) else "file"
        
        # Find and highlight the selected item with prominent Windows-style selection
        for i, item_frame in enumerate(self.icon_items):
            # Get item name for this frame
            if i < len(self.current_directory.subdirectories):
                frame_item_name = self.current_directory.subdirectories[i].name
            else:
                file_index = i - len(self.current_directory.subdirectories)
                if file_index < len(self.current_directory.files):
                    frame_item_name = self.current_directory.files[file_index].name
                else:
                    continue
            
            # Highlight if this is the selected item
            if frame_item_name == item_name:
                self.highlight_item(item_frame, True)
                break
        
        # Update selection status
        self.update_selection_status()
        
        # Dismiss context menus
        self.dismiss_context_menus()

    def on_directory_select(self, event):
        selection = self.directory_tree.selection()
        if not selection:
            return
        
        item = selection[0]
        # Get the directory name from the tree item (no more [DIR] suffix)
        dir_name = self.directory_tree.item(item, "text")
        
        directory = find_directory(dir_name)
        if directory:
            self.navigate_to_directory(directory)

    def on_directory_right_click(self, event):
        # Dismiss any existing context menus first
        self.dismiss_context_menus()
        
        item = self.directory_tree.identify_row(event.y)
        if item:
            self.directory_tree.selection_set(item)
            self.selected_item = self.directory_tree.item(item, "text")
            self.selected_item_type = "directory"
            
            # Create a fresh context menu each time
            self.dir_context_menu = tk.Menu(self.master, tearoff=0)
            self.dir_context_menu.add_command(label="Open", command=self.open_directory)
            
            # Only allow renaming for non-root directories and not Trash
            protected_dirs = ["Documents", "Media", "Projects", "System", "Trash"]
            if self.selected_item not in protected_dirs:
                self.dir_context_menu.add_command(label="Rename", command=self.rename_directory)
            
            self.dir_context_menu.add_separator()
            
            # Cut/Copy operations (not for root directories or Trash)
            if self.selected_item not in protected_dirs:
                self.dir_context_menu.add_command(label="Cut (Ctrl+X)", command=self.cut_selected)
                self.dir_context_menu.add_command(label="Copy (Ctrl+C)", command=self.copy_selected)
                self.dir_context_menu.add_separator()
            
            self.dir_context_menu.add_command(label="Create File", command=self.create_file_in_selected)
            self.dir_context_menu.add_command(label="Create Directory", command=self.create_directory_in_selected)
            self.dir_context_menu.add_separator()
            
            # Add paste option
            self.dir_context_menu.add_command(label="Paste (Ctrl+V)", command=self.paste_to_selected)
            paste_state = tk.NORMAL if can_paste_here(find_directory(self.selected_item)) else tk.DISABLED
            self.dir_context_menu.entryconfig("Paste (Ctrl+V)", state=paste_state)
            self.dir_context_menu.add_separator()
            
            # Only allow deletion for subdirectories (not root directories or Trash)
            if self.selected_item not in protected_dirs:
                self.dir_context_menu.add_command(label="Delete", command=self.delete_selected_directory)
            
            # Add "Empty Trash" option only if this is the Trash directory
            if self.selected_item == "Trash":
                self.dir_context_menu.add_command(label="Empty Trash", command=self.empty_trash)
            
            self.dir_context_menu.post(event.x_root, event.y_root)

    def on_icon_right_click(self, event, item_name):
        """Updated right-click handler with proper mixed selection support"""
        # Dismiss any existing context menus first
        self.dismiss_context_menus()

        # Debug: Print current selection state
        print(f"Right-click on: {item_name}")
        print(f"Current selected_items: {self.selected_items}")
        print(f"Selection count: {len(self.selected_items)}")
        
        # Debug: Check what menus exist
        print(f"Has mixed_context_menu: {hasattr(self, 'mixed_context_menu')}")
        print(f"Has trash_mixed_context_menu: {hasattr(self, 'trash_mixed_context_menu')}")

        # Check if multiple items are already selected BEFORE setting selected_item
        has_multiple_selection = len(self.selected_items) > 1
        print(f"Has multiple selection: {has_multiple_selection}")
        
        # If clicking on an item that's already part of the selection, don't change selection
        if item_name in self.selected_items:
            # Keep the existing selection
            print(f"Item {item_name} is part of existing selection - preserving multi-selection")
            pass
        else:
            # Single click on new item - update selection
            print(f"Item {item_name} not in selection - setting as single selection")
            self.selected_item = item_name
            self.selected_items = [item_name]

        # Check if it's a directory or file
        is_directory = any(subdir.name == item_name for subdir in self.current_directory.subdirectories)
        self.selected_item_type = "directory" if is_directory else "file"

        # Handle trash directory with mixed selection support
        if self.current_directory and self.current_directory.name == "Trash":
            # Check if multiple items are selected
            if has_multiple_selection or len(self.selected_items) > 1:
                # Mixed selection in trash - show mixed context menu
                print("Showing trash mixed context menu")
                self.trash_mixed_context_menu.post(event.x_root, event.y_root)
            elif is_directory:
                # Single directory in trash
                print("Showing trash directory context menu")
                self.trash_dir_context_menu.post(event.x_root, event.y_root)
            else:
                # Single file in trash
                print("Showing trash file context menu")
                self.trash_file_context_menu.post(event.x_root, event.y_root)
            return

        # Handle regular directories (not in trash)
        # Check if multiple items are selected
        if has_multiple_selection or len(self.selected_items) > 1:
            # Mixed selection in regular directory - show mixed context menu
            print("Showing mixed context menu for regular directory")
            self.mixed_context_menu.post(event.x_root, event.y_root)
            return

        # Handle single item selection in regular directories
        if is_directory:
            print("Showing single directory context menu")
            # Create dynamic directory context menu for normal directories
            self.dynamic_dir_context_menu = tk.Menu(self.master, tearoff=0)

            # Always allow opening
            self.dynamic_dir_context_menu.add_command(label="Open", command=self.open_directory)

            # Only allow renaming for non-system directories
            protected_dirs = ["Documents", "Media", "Projects", "System", "Trash"]
            if item_name not in protected_dirs:
                self.dynamic_dir_context_menu.add_command(label="Rename", command=self.rename_directory)

            self.dynamic_dir_context_menu.add_separator()

            # Cut/Copy operations (not for system directories)
            if item_name not in protected_dirs:
                self.dynamic_dir_context_menu.add_command(label="Cut (Ctrl+X)", command=self.cut_selected)
                self.dynamic_dir_context_menu.add_command(label="Copy (Ctrl+C)", command=self.copy_selected)
                self.dynamic_dir_context_menu.add_separator()

            self.dynamic_dir_context_menu.add_command(label="Create File", command=self.create_file_in_selected)
            self.dynamic_dir_context_menu.add_command(label="Create Directory", command=self.create_directory_in_selected)
            self.dynamic_dir_context_menu.add_separator()

            # Add paste option
            self.dynamic_dir_context_menu.add_command(label="Paste (Ctrl+V)", command=self.paste_to_selected)
            paste_state = tk.NORMAL if can_paste_here(find_directory(item_name)) else tk.DISABLED
            self.dynamic_dir_context_menu.entryconfig("Paste (Ctrl+V)", state=paste_state)
            self.dynamic_dir_context_menu.add_separator()

            # Only allow deletion for non-system directories
            if item_name not in protected_dirs:
                self.dynamic_dir_context_menu.add_command(label="Delete", command=self.delete_selected_directory)

            # Add "Empty Trash" option only if this is the Trash directory
            if item_name == "Trash":
                self.dynamic_dir_context_menu.add_command(label="Empty Trash", command=self.empty_trash)

            # Always add refresh option
            self.dynamic_dir_context_menu.add_separator()
            self.dynamic_dir_context_menu.add_command(label="Refresh", command=self.refresh_all)

            self.dynamic_dir_context_menu.post(event.x_root, event.y_root)

        else:
            # Normal file handling
            print("Showing single file context menu")
            self.file_context_menu.post(event.x_root, event.y_root)

    def refresh_directory_tree(self):
        """Refresh the directory tree and ensure it's visible"""
        self.directory_tree.delete(*self.directory_tree.get_children())
        # Only show root directories - no subdirectories
        for root_dir in root_directories:
            self.insert_directory_tree("", root_dir)
        
        # Ensure the tree is expanded and visible
        for item in self.directory_tree.get_children():
            self.directory_tree.item(item, open=True)
        
        # Reapply custom styling to ensure it persists
        self.apply_custom_treeview_styling()
        
        print(f"Directory tree refreshed with {len(root_directories)} directories")

    def insert_directory_tree(self, parent, directory):
        """Insert directory into the tree view"""
        # Choose appropriate icon (small icons for directory tree)
        icon = self.get_folder_icon(directory.name, large=False)
        
        # Just use directory name without [DIR] suffix
        dir_text = directory.name
        
        if icon:
            node = self.directory_tree.insert(parent, "end", text=dir_text, image=icon, open=True)
        else:
            node = self.directory_tree.insert(parent, "end", text=dir_text, open=True)
        
        print(f"Added directory '{dir_text}' to tree")

    def refresh_content(self):
        # Clear selections
        self.clear_selection()
        
        # Clear icon grid
        if hasattr(self, 'icon_items'):
            for item in self.icon_items:
                item.destroy()
            self.icon_items = []
        
        if not self.current_directory:
            return
        
        # Populate icon view
        self.populate_icon_view()

    def populate_icon_view(self):
        """Populate the icon view with directories and files in a grid"""
        # Get current canvas background for consistency
        canvas_bg = self.icon_canvas.cget('bg')
        
        # Update the grid frame background to match canvas
        self.icon_grid_frame.config(bg=canvas_bg)
        
        # Add subdirectories
        for subdir in self.current_directory.subdirectories:
            icon = self.get_folder_icon(subdir.name, large=True)
            item = self.create_icon_item(subdir.name, icon, is_directory=True)
            self.icon_items.append(item)
        
        # Add files
        for file in self.current_directory.files:
            file_icon = self.get_file_icon(file.name, file.permissions, large=True)
            item = self.create_icon_item(file.name, file_icon, is_directory=False)
            self.icon_items.append(item)
        
        # Update grid layout
        self.master.after_idle(self.update_icon_grid)
        self.master.after_idle(lambda: self.icon_canvas.configure(scrollregion=self.icon_canvas.bbox("all")))

    def search(self):
        query = self.search_entry.get().lower()
        if not query:
            self.refresh_content()
            return
        
        # Clear selections
        self.clear_selection()
        
        # Clear existing content
        if hasattr(self, 'icon_items'):
            for item in self.icon_items:
                item.destroy()
            self.icon_items = []
        
        if not self.current_directory:
            return
        
        # Search in current directory
        for subdir in self.current_directory.subdirectories:
            if query in subdir.name.lower():
                icon = self.get_folder_icon(subdir.name, large=True)
                item = self.create_icon_item(subdir.name, icon, is_directory=True)
                self.icon_items.append(item)
        
        for file in self.current_directory.files:
            if query in file.name.lower():
                file_icon = self.get_file_icon(file.name, file.permissions, large=True)
                item = self.create_icon_item(file.name, file_icon, is_directory=False)
                self.icon_items.append(item)
        
        # Update grid layout
        self.master.after_idle(self.update_icon_grid)
        self.master.after_idle(lambda: self.icon_canvas.configure(scrollregion=self.icon_canvas.bbox("all")))

    # Cut/Copy/Paste operations
    def cut_selected(self):
        """Cut the selected items"""
        if not self.selected_items or not self.current_directory:
            return
        
        items = []
        for item_name in self.selected_items:
            # Check if it's a file
            for file in self.current_directory.files:
                if file.name == item_name:
                    items.append(file)
                    break
            else:
                # Check if it's a directory
                for subdir in self.current_directory.subdirectories:
                    if subdir.name == item_name:
                        items.append(subdir)
                        break
        
        if items:
            copy_to_clipboard(items, "cut", self.current_directory)

    def copy_selected(self):
        """Copy the selected items"""
        if not self.selected_items or not self.current_directory:
            return
        
        items = []
        for item_name in self.selected_items:
            # Check if it's a file
            for file in self.current_directory.files:
                if file.name == item_name:
                    items.append(file)
                    break
            else:
                # Check if it's a directory
                for subdir in self.current_directory.subdirectories:
                    if subdir.name == item_name:
                        items.append(subdir)
                        break
        
        if items:
            copy_to_clipboard(items, "copy", self.current_directory)

    def paste_to_current(self):
        """Paste items to current directory"""
        if not self.current_directory:
            return
        
        msg = paste_items(self.current_directory)
        if msg.startswith("Error"):
            messagebox.showerror("Paste Error", msg)
        else:
            # Silent success - just refresh the view
            self.refresh_all()

    def paste_to_selected(self):
        """Paste items to selected directory"""
        if not self.selected_item or self.selected_item_type != "directory":
            return
        
        target_dir = find_directory(self.selected_item)
        if not target_dir:
            return
        
        msg = paste_items(target_dir)
        if msg.startswith("Error"):
            messagebox.showerror("Paste Error", msg)
        else:
            # Silent success - just refresh the view
            self.refresh_all()

    # Context menu actions
    def open_directory(self):
        if self.selected_item and self.selected_item_type == "directory":
            directory = find_directory(self.selected_item)
            if directory:
                self.navigate_to_directory(directory)

    def create_file_in_selected(self):
        if not self.selected_item:
            return
        directory = find_directory(self.selected_item)
        if directory:
            self._create_file_dialog(directory)

    def create_file_in_current(self):
        if self.current_directory:
            self._create_file_dialog(self.current_directory)

    def _create_file_dialog(self, directory):
        filename = simpledialog.askstring("Create File", "Enter file name:")
        if not filename:
            return
        
        # Auto-add .txt extension if no extension provided
        if '.' not in filename:
            filename += '.txt'
        
        # Default permissions: 1 = Read-Write (no user prompt)
        perm = 1
        
        # Use default allocation method (Contiguous)
        alloc = "Contiguous"
        
        msg = directory.create_file(filename, alloc, perm)
        # Only show error messages, not success messages
        if msg.startswith("Error"):
            messagebox.showerror("Error", msg)
        self.refresh_all()

    def create_directory_in_selected(self):
        if not self.selected_item:
            return
        directory = find_directory(self.selected_item)
        if directory:
            self._create_directory_dialog(directory)

    def create_directory_in_current(self):
        if self.current_directory:
            self._create_directory_dialog(self.current_directory)

    def _create_directory_dialog(self, directory):
        dirname = simpledialog.askstring("Create Directory", "Enter directory name:")
        if not dirname:
            return
        
        msg = directory.create_subdirectory(dirname)
        # Only show error messages, not success messages
        if msg.startswith("Error"):
            messagebox.showerror("Error", msg)
        self.refresh_all()

    def rename_directory(self):
        """Improved directory rename with better handling for subdirectories"""
        if not self.selected_item:
            return

        # Check if this is a protected root directory
        protected_dirs = ["Documents", "Media", "Projects", "System", "Trash"]
        if self.selected_item in protected_dirs:
            messagebox.showerror("Error", "Cannot rename system directories.")
            return

        # Pre-populate with current name
        new_name = simpledialog.askstring("Rename Directory", 
                                         f"Enter new name for '{self.selected_item}':",
                                         initialvalue=self.selected_item)
        if not new_name or new_name == self.selected_item:
            return

        # Handle root directory renaming
        for root in root_directories:
            if root.name == self.selected_item:
                # Check if new name already exists
                if any(r.name == new_name for r in root_directories):
                    messagebox.showerror("Error", f"Directory '{new_name}' already exists.")
                    return
                root.name = new_name
                self.refresh_all()
                return

        # Handle subdirectory renaming in current directory
        if self.current_directory:
            # Check if new name already exists in current directory
            if any(d.name == new_name for d in self.current_directory.subdirectories):
                messagebox.showerror("Error", f"Directory '{new_name}' already exists.")
                return

            msg = self.current_directory.rename_subdirectory(self.selected_item, new_name)
            if msg.startswith("Error"):
                messagebox.showerror("Error", msg)
            else:
                self.refresh_content()
                return
    
        # If we get here, directory wasn't found
        messagebox.showerror("Error", f"Directory '{self.selected_item}' not found.")

    def rename_file(self):
        """Improved file rename with pre-populated name and automatic extension handling"""
        if not self.selected_item or not self.current_directory:
            return
        
        current_name = self.selected_item
        
        # Extract filename without extension
        if '.' in current_name:
            name_without_ext = '.'.join(current_name.split('.')[:-1])
            extension = '.' + current_name.split('.')[-1]
        else:
            name_without_ext = current_name
            extension = ""
        
        # Ask for new name (without extension) and pre-populate with current name
        new_name_without_ext = simpledialog.askstring(
            "Rename File", 
            f"Enter new name for '{current_name}':\n(Extension '{extension}' will be added automatically)",
            initialvalue=name_without_ext
        )
        
        if not new_name_without_ext:
            return
        
        # Remove any extension user might have typed (we'll add the original back)
        if '.' in new_name_without_ext:
            new_name_without_ext = '.'.join(new_name_without_ext.split('.')[:-1])
        
        # Reconstruct the full filename with original extension
        new_full_name = new_name_without_ext + extension
        
        # Check if the name actually changed
        if new_full_name == current_name:
            return
        
        # Check if file with new name already exists
        if any(f.name == new_full_name for f in self.current_directory.files):
            messagebox.showerror("Error", f"File '{new_full_name}' already exists.")
            return
        
        msg = self.current_directory.rename_file(self.selected_item, new_full_name)
        if msg.startswith("Error"):
            messagebox.showerror("Error", msg)
        else:
            self.refresh_content()

    def delete_selected_directory(self):
        """Delete selected directory(ies) to trash - SIMPLIFIED CONFIRMATION"""
        if not self.selected_item:
            return

        if current_user["role"] != UserRole.ADMIN:
            messagebox.showerror("Error", "Only ADMIN can delete directories.")
            return

        # Handle multiple selection for directories in current directory
        if len(self.selected_items) > 1:
            # Get ALL directory names that exist in current directory
            dir_names = []
            for item_name in self.selected_items:
                if any(d.name == item_name for d in self.current_directory.subdirectories):
                    dir_names.append(item_name)

            if not dir_names:
                return

            # SIMPLIFIED confirmation - NO DIRECTORY LIST
            result = messagebox.askyesno("Confirm Delete", 
                                       f"Are you sure you want to move {len(dir_names)} directory(ies) to trash?")
            if not result:
                return

            # Delete each selected directory - CREATE A COPY TO AVOID MODIFICATION DURING ITERATION
            dirs_to_delete = dir_names.copy()
            success_count = 0
            error_messages = []

            for dirname in dirs_to_delete:
                try:
                    # Find directory and move to trash
                    for subdir in self.current_directory.subdirectories:
                        if subdir.name == dirname:
                            # Store original location and parent for restore functionality
                            subdir.original_location = self.current_directory.name
                            subdir.original_parent = self.current_directory
                            trash_dir.subdirectories.append(subdir)
                            self.current_directory.subdirectories.remove(subdir)
                            success_count += 1
                            break
                    else:
                        error_messages.append(f"Directory '{dirname}' not found")
                except Exception as e:
                    error_messages.append(f"Error deleting '{dirname}': {str(e)}")

            # Show results - SIMPLIFIED
            if error_messages:
                messagebox.showerror("Deletion Errors", 
                                   f"Successfully moved {success_count} directory(ies) to trash.\n\n{len(error_messages)} directory(ies) had errors.")

            self.clear_selection()
            self.refresh_all()
            return

        # Handle single selection - use existing logic but improved
        result = messagebox.askyesno("Confirm Delete", f"Are you sure you want to move '{self.selected_item}' to trash?")
        if not result:
            return

        # Handle root directory deletion - move to trash
        for i, root in enumerate(root_directories):
            if root.name == self.selected_item:
                if root.name not in ["Trash", "Documents", "Media", "Projects", "System"]:  # Prevent deleting protected directories
                    # Move to trash
                    root.original_location = "Root"
                    root.original_parent = None  # Special case for root directories
                    trash_dir.subdirectories.append(root)
                    root_directories.remove(root)
                    self.refresh_all()
                    return
                else:
                    messagebox.showerror("Error", "Cannot delete protected system directories.")
                    return

        # Handle subdirectory deletion from current directory - move to trash
        if self.current_directory:
            for subdir in self.current_directory.subdirectories:
                if subdir.name == self.selected_item:
                    # Store original location and parent for restore functionality
                    subdir.original_location = self.current_directory.name
                    subdir.original_parent = self.current_directory
                    trash_dir.subdirectories.append(subdir)
                    self.current_directory.subdirectories.remove(subdir)
                    self.refresh_all()
                    return

        # If we reach here, directory wasn't found
        messagebox.showerror("Error", f"Directory '{self.selected_item}' not found.")

    def delete_selected_file(self):
        """Delete selected file(s) to trash - SIMPLIFIED CONFIRMATION"""
        if not self.current_directory:
            return

        # Handle multiple selection
        if len(self.selected_items) > 1:
            # Get ALL file names that exist in current directory
            file_names = []
            for item_name in self.selected_items:
                if any(f.name == item_name for f in self.current_directory.files):
                    file_names.append(item_name)

            if not file_names:
                return

            # SIMPLIFIED confirmation - NO FILE LIST
            result = messagebox.askyesno("Confirm Delete", 
                                       f"Are you sure you want to move {len(file_names)} file(s) to trash?")
            if not result:
                return

            # Delete each selected file - CREATE A COPY TO AVOID MODIFICATION DURING ITERATION
            files_to_delete = file_names.copy()
            success_count = 0
            error_messages = []

            for filename in files_to_delete:
                # Use the existing delete_file method
                msg = self.current_directory.delete_file(filename)
                if msg.startswith("Error"):
                    error_messages.append(f"{filename}: {msg}")
                else:
                    success_count += 1

            # Show results - SIMPLIFIED
            if error_messages:
                messagebox.showerror("Deletion Errors", 
                                   f"Successfully moved {success_count} file(s) to trash.\n\n{len(error_messages)} file(s) had errors.")

            self.clear_selection()
            self.refresh_content()
            return

        # Handle single selection - use existing logic
        if not self.selected_item:
            return

        result = messagebox.askyesno("Confirm Delete", f"Are you sure you want to move '{self.selected_item}' to trash?")
        if not result:
            return

        msg = self.current_directory.delete_file(self.selected_item)
        if msg.startswith("Error"):
            messagebox.showerror("Error", msg)
        self.refresh_content()

    def restore_selected_file(self):
        """Restore selected file(s) from trash - SIMPLIFIED CONFIRMATION"""
        if not self.current_directory:
            return

        if self.current_directory.name != "Trash":
            messagebox.showerror("Error", "Can only restore files from Trash.")
            return

        # Handle multiple selection - GET ALL SELECTED FILES
        if len(self.selected_items) > 1:
            # Get ALL file names that exist in current directory
            file_names = []
            for item_name in self.selected_items:
                # Check if this item is actually a file in the current directory
                if any(f.name == item_name for f in self.current_directory.files):
                    file_names.append(item_name)

            if not file_names:
                messagebox.showerror("Error", "No files selected for restoration.")
                return

            # SIMPLIFIED confirmation - NO FILE LIST
            result = messagebox.askyesno("Confirm Restore", 
                                       f"Are you sure you want to restore {len(file_names)} file(s)?")
            if not result:
                return

            # Restore each selected file - CREATE A COPY OF THE LIST TO AVOID MODIFICATION DURING ITERATION
            files_to_restore = file_names.copy()
            success_count = 0
            error_messages = []

            for filename in files_to_restore:
                try:
                    # Find the file object
                    file_to_restore = None
                    for f in self.current_directory.files:
                        if f.name == filename:
                            file_to_restore = f
                            break
                        
                    if file_to_restore and file_to_restore.original_location:
                        # Find the original directory
                        original_dir = find_directory(file_to_restore.original_location)
                        if original_dir:
                            # Check if file with same name already exists in original location
                            if not any(f.name == filename for f in original_dir.files):
                                # Move file back to original location
                                file_to_restore.original_location = None  # Clear the trash marker
                                original_dir.files.append(file_to_restore)
                                self.current_directory.files.remove(file_to_restore)
                                success_count += 1
                                print(f"Successfully restored file: {filename}")
                            else:
                                error_messages.append(f"File '{filename}' already exists in original location")
                        else:
                            error_messages.append(f"Original location for '{filename}' not found")
                    else:
                        error_messages.append(f"File '{filename}' has no original location information")
                except Exception as e:
                    error_messages.append(f"Error restoring '{filename}': {str(e)}")

            # Show results - SIMPLIFIED
            if error_messages:
                messagebox.showerror("Restore Errors", 
                                   f"Successfully restored {success_count} file(s).\n\n{len(error_messages)} file(s) had errors.")
            else:
                messagebox.showinfo("Restore Complete", 
                                  f"Successfully restored {success_count} file(s).")

            # Clear selection and refresh
            self.clear_selection()
            self.refresh_content()
            self.refresh_directory_tree()
            return

        # Handle single selection
        if not self.selected_item:
            messagebox.showerror("Error", "No file selected for restoration.")
            return

        # Restore single file using the existing method
        msg = self.current_directory.restore_file(self.selected_item)
        if msg.startswith("Error"):
            messagebox.showerror("Error", msg)
        else:
            messagebox.showinfo("Restore Complete", msg)
        self.refresh_content()
        self.refresh_directory_tree()

    def restore_selected_directory(self):
        """Restore selected directory(ies) from trash - SIMPLIFIED CONFIRMATION"""
        if not self.current_directory:
            return

        if self.current_directory.name != "Trash":
            messagebox.showerror("Error", "Can only restore directories from Trash.")
            return

        # Handle multiple selection - GET ALL SELECTED DIRECTORIES
        if len(self.selected_items) > 1:
            # Get ALL directory names that exist in current directory
            dir_names = []
            for item_name in self.selected_items:
                # Check if this item is actually a directory in the current directory
                if any(d.name == item_name for d in self.current_directory.subdirectories):
                    dir_names.append(item_name)

            if not dir_names:
                messagebox.showerror("Error", "No directories selected for restoration.")
                return

            # SIMPLIFIED confirmation - NO DIRECTORY LIST
            result = messagebox.askyesno("Confirm Restore", 
                                       f"Are you sure you want to restore {len(dir_names)} directory(ies)?")
            if not result:
                return

            # Restore each selected directory - CREATE A COPY OF THE LIST TO AVOID MODIFICATION DURING ITERATION
            dirs_to_restore = dir_names.copy()
            success_count = 0
            error_messages = []

            for dirname in dirs_to_restore:
                try:
                    # Find the directory object
                    dir_to_restore = None
                    for d in self.current_directory.subdirectories:
                        if d.name == dirname:
                            dir_to_restore = d
                            break
                        
                    if dir_to_restore and dir_to_restore.original_parent:
                        # Check if directory with same name already exists in original location
                        if not any(d.name == dirname for d in dir_to_restore.original_parent.subdirectories):
                            # Move directory back to original location
                            dir_to_restore.original_parent.subdirectories.append(dir_to_restore)
                            dir_to_restore.original_location = None
                            dir_to_restore.original_parent = None
                            self.current_directory.subdirectories.remove(dir_to_restore)
                            success_count += 1
                            print(f"Successfully restored directory: {dirname}")
                        else:
                            error_messages.append(f"Directory '{dirname}' already exists in original location")
                    else:
                        error_messages.append(f"Directory '{dirname}' has no original location information")
                except Exception as e:
                    error_messages.append(f"Error restoring '{dirname}': {str(e)}")

            # Show results - SIMPLIFIED
            if error_messages:
                messagebox.showerror("Restore Errors", 
                                   f"Successfully restored {success_count} directory(ies).\n\n{len(error_messages)} directory(ies) had errors.")

            # Clear selection and refresh
            self.clear_selection()
            self.refresh_content()
            self.refresh_directory_tree()
            return

        # Handle single selection
        if not self.selected_item:
            messagebox.showerror("Error", "No directory selected for restoration.")
            return

        # Restore single directory using the existing method
        msg = self.current_directory.restore_directory(self.selected_item)
        if msg.startswith("Error"):
            messagebox.showerror("Error", msg)
        else:
            messagebox.showinfo("Restore Complete", msg)
        self.refresh_content()
        self.refresh_directory_tree()

    def delete_permanently_selected_file(self):
        """Permanently delete selected file(s) from trash - SIMPLIFIED CONFIRMATION"""
        if not self.current_directory:
            return

        if self.current_directory.name != "Trash":
            messagebox.showerror("Error", "Can only permanently delete files from Trash.")
            return

        # Handle multiple selection - GET ALL SELECTED FILES
        if len(self.selected_items) > 1:
            # Get ALL file names that exist in current directory
            file_names = []
            for item_name in self.selected_items:
                # Check if this item is actually a file in the current directory
                if any(f.name == item_name for f in self.current_directory.files):
                    file_names.append(item_name)

            if not file_names:
                messagebox.showerror("Error", "No files selected for deletion.")
                return

            # SIMPLIFIED confirmation - NO FILE LIST
            result = messagebox.askyesno("Confirm Permanent Delete", 
                                       f"Are you sure you want to permanently delete {len(file_names)} file(s)?\n\nThis action cannot be undone!")
            if not result:
                return

            # Delete each selected file - CREATE A COPY OF THE LIST TO AVOID MODIFICATION DURING ITERATION
            files_to_delete = file_names.copy()
            success_count = 0
            error_messages = []

            for filename in files_to_delete:
                try:
                    # Find the file object
                    file_to_delete = None
                    for f in self.current_directory.files:
                        if f.name == filename:
                            file_to_delete = f
                            break
                        
                    if file_to_delete:
                        # Remove from the files list
                        self.current_directory.files.remove(file_to_delete)
                        success_count += 1
                        print(f"Successfully deleted file: {filename}")
                    else:
                        error_messages.append(f"File '{filename}' not found")
                except Exception as e:
                    error_messages.append(f"Error deleting '{filename}': {str(e)}")

            # Show results - SIMPLIFIED
            if error_messages:
                messagebox.showerror("Deletion Errors", 
                                   f"Successfully deleted {success_count} file(s).\n\n{len(error_messages)} file(s) had errors.")
            else:
                messagebox.showinfo("Deletion Complete", 
                                  f"Successfully deleted {success_count} file(s) permanently.")

            # Clear selection after deletion
            self.clear_selection()
            self.refresh_content()
            return

        # Handle single selection
        if not self.selected_item:
            messagebox.showerror("Error", "No file selected for deletion.")
            return

        result = messagebox.askyesno("Confirm Permanent Delete", 
                                   f"Are you sure you want to permanently delete '{self.selected_item}'?\nThis action cannot be undone!")
        if not result:
            return

        # Delete single file
        try:
            file_to_delete = None
            for f in self.current_directory.files:
                if f.name == self.selected_item:
                    file_to_delete = f
                    break
                
            if file_to_delete:
                self.current_directory.files.remove(file_to_delete)
            else:
                messagebox.showerror("Error", f"File '{self.selected_item}' not found.")
        except Exception as e:
            messagebox.showerror("Error", f"Error deleting file: {str(e)}")

        self.refresh_content()

    def delete_mixed_selection_to_trash(self):
        """Move mixed selection of files and directories to trash"""
        if not self.current_directory:
            return

        if not self.selected_items:
            return

        if current_user["role"] != UserRole.ADMIN:
            messagebox.showerror("Error", "Only ADMIN can delete.")
            return

        # Separate files and directories from the selection
        file_names = [name for name in self.selected_items 
                     if any(f.name == name for f in self.current_directory.files)]
        dir_names = [name for name in self.selected_items 
                    if any(d.name == name for d in self.current_directory.subdirectories)]

        total_items = len(file_names) + len(dir_names)
        
        if total_items == 0:
            return

        # Confirmation dialog for mixed selection
        if total_items > 1:
            item_breakdown = []
            if file_names:
                item_breakdown.append(f"{len(file_names)} file(s)")
            if dir_names:
                item_breakdown.append(f"{len(dir_names)} directory(ies)")
            
            items_text = " and ".join(item_breakdown)
            
            result = messagebox.askyesno("Confirm Delete", 
                                       f"Are you sure you want to move {items_text} to trash?")
            if not result:
                return
        else:
            # Single item - show simple confirmation
            item_name = self.selected_items[0]
            result = messagebox.askyesno("Confirm Delete", f"Are you sure you want to move '{item_name}' to trash?")
            if not result:
                return

        success_count = 0
        error_messages = []

        # Delete files first (move to trash)
        for filename in file_names:
            try:
                file_to_delete = None
                for f in self.current_directory.files:
                    if f.name == filename:
                        file_to_delete = f
                        break
                    
                if file_to_delete:
                    if file_to_delete.permissions == 0:
                        error_messages.append(f"Cannot delete read-only file '{filename}'")
                        continue
                    
                    # Store original location for restore functionality
                    file_to_delete.original_location = self.current_directory.name
                    trash_dir.files.append(file_to_delete)
                    self.current_directory.files.remove(file_to_delete)
                    success_count += 1
                    print(f"Successfully moved file to trash: {filename}")
                else:
                    error_messages.append(f"File '{filename}' not found")
            except Exception as e:
                error_messages.append(f"Error deleting file '{filename}': {str(e)}")

        # Delete directories (move to trash)
        for dirname in dir_names:
            try:
                dir_to_delete = None
                for d in self.current_directory.subdirectories:
                    if d.name == dirname:
                        dir_to_delete = d
                        break
                    
                if dir_to_delete:
                    # Store original location and parent for restore functionality
                    dir_to_delete.original_location = self.current_directory.name
                    dir_to_delete.original_parent = self.current_directory
                    trash_dir.subdirectories.append(dir_to_delete)
                    self.current_directory.subdirectories.remove(dir_to_delete)
                    success_count += 1
                    print(f"Successfully moved directory to trash: {dirname}")
                else:
                    error_messages.append(f"Directory '{dirname}' not found")
            except Exception as e:
                error_messages.append(f"Error deleting directory '{dirname}': {str(e)}")

        # Show results only if there were errors
        if error_messages:
            messagebox.showerror("Deletion Errors", 
                               f"Successfully moved {success_count} item(s) to trash.\n\n{len(error_messages)} item(s) had errors.")

        # Refresh views
        self.refresh_content()
        self.refresh_directory_tree()

    def restore_mixed_selection(self):
        """Restore mixed selection of files and directories from trash"""
        if not self.current_directory:
            return

        if self.current_directory.name != "Trash":
            messagebox.showerror("Error", "Can only restore from Trash.")
            return

        if not self.selected_items:
            messagebox.showerror("Error", "No items selected for restoration.")
            return

        # Separate files and directories from the selection
        file_names = [name for name in self.selected_items 
                     if any(f.name == name for f in self.current_directory.files)]
        dir_names = [name for name in self.selected_items 
                    if any(d.name == name for d in self.current_directory.subdirectories)]

        total_items = len(file_names) + len(dir_names)
        
        if total_items == 0:
            messagebox.showerror("Error", "No valid items selected for restoration.")
            return

        # Confirmation dialog
        item_breakdown = []
        if file_names:
            item_breakdown.append(f"{len(file_names)} file(s)")
        if dir_names:
            item_breakdown.append(f"{len(dir_names)} directory(ies)")
        
        items_text = " and ".join(item_breakdown)
        
        result = messagebox.askyesno("Confirm Restore", 
                                   f"Are you sure you want to restore {items_text}?")
        if not result:
            return

        success_count = 0
        error_messages = []

        # Restore files first
        for filename in file_names:
            try:
                file_to_restore = None
                for f in self.current_directory.files:
                    if f.name == filename:
                        file_to_restore = f
                        break
                    
                if file_to_restore and file_to_restore.original_location:
                    original_dir = find_directory(file_to_restore.original_location)
                    if original_dir:
                        if not any(f.name == filename for f in original_dir.files):
                            file_to_restore.original_location = None
                            original_dir.files.append(file_to_restore)
                            self.current_directory.files.remove(file_to_restore)
                            success_count += 1
                            print(f"Successfully restored file: {filename}")
                        else:
                            error_messages.append(f"File '{filename}' already exists in original location")
                    else:
                        error_messages.append(f"Original location for file '{filename}' not found")
                else:
                    error_messages.append(f"File '{filename}' has no original location information")
            except Exception as e:
                error_messages.append(f"Error restoring file '{filename}': {str(e)}")

        # Restore directories
        for dirname in dir_names:
            try:
                dir_to_restore = None
                for d in self.current_directory.subdirectories:
                    if d.name == dirname:
                        dir_to_restore = d
                        break
                    
                if dir_to_restore and dir_to_restore.original_parent:
                    if not any(d.name == dirname for d in dir_to_restore.original_parent.subdirectories):
                        dir_to_restore.original_parent.subdirectories.append(dir_to_restore)
                        dir_to_restore.original_location = None
                        dir_to_restore.original_parent = None
                        self.current_directory.subdirectories.remove(dir_to_restore)
                        success_count += 1
                        print(f"Successfully restored directory: {dirname}")
                    else:
                        error_messages.append(f"Directory '{dirname}' already exists in original location")
                else:
                    error_messages.append(f"Directory '{dirname}' has no original location information")
            except Exception as e:
                error_messages.append(f"Error restoring directory '{dirname}': {str(e)}")

        # Show results
        if error_messages:
            messagebox.showerror("Restore Errors", 
                               f"Successfully restored {success_count} item(s).\n\n{len(error_messages)} item(s) had errors.")
        else:
            if success_count > 0:
                messagebox.showinfo("Restore Complete", 
                                  f"Successfully restored {success_count} item(s).")

        # Clear selection and refresh
        self.clear_selection()
        self.refresh_content()
        self.refresh_directory_tree()

    def delete_permanently_mixed_selection(self):
        """Permanently delete mixed selection of files and directories from trash"""
        if not self.current_directory:
            return

        if self.current_directory.name != "Trash":
            messagebox.showerror("Error", "Can only permanently delete from Trash.")
            return

        if not self.selected_items:
            messagebox.showerror("Error", "No items selected for deletion.")
            return

        # Separate files and directories from the selection
        file_names = [name for name in self.selected_items 
                     if any(f.name == name for f in self.current_directory.files)]
        dir_names = [name for name in self.selected_items 
                    if any(d.name == name for d in self.current_directory.subdirectories)]

        total_items = len(file_names) + len(dir_names)
        
        if total_items == 0:
            messagebox.showerror("Error", "No valid items selected for deletion.")
            return

        # Confirmation dialog for mixed selection
        item_breakdown = []
        if file_names:
            item_breakdown.append(f"{len(file_names)} file(s)")
        if dir_names:
            item_breakdown.append(f"{len(dir_names)} directory(ies)")
        
        items_text = " and ".join(item_breakdown)
        
        result = messagebox.askyesno("Confirm Permanent Delete", 
                                   f"Are you sure you want to permanently delete {items_text}?\n\nThis action cannot be undone!")
        if not result:
            return

        success_count = 0
        error_messages = []

        # Delete files first
        for filename in file_names:
            try:
                file_to_delete = None
                for f in self.current_directory.files:
                    if f.name == filename:
                        file_to_delete = f
                        break
                    
                if file_to_delete:
                    self.current_directory.files.remove(file_to_delete)
                    success_count += 1
                    print(f"Successfully deleted file: {filename}")
                else:
                    error_messages.append(f"File '{filename}' not found")
            except Exception as e:
                error_messages.append(f"Error deleting file '{filename}': {str(e)}")

        # Delete directories
        for dirname in dir_names:
            try:
                dir_to_delete = None
                for d in self.current_directory.subdirectories:
                    if d.name == dirname:
                        dir_to_delete = d
                        break
                    
                if dir_to_delete:
                    self.current_directory.subdirectories.remove(dir_to_delete)
                    success_count += 1
                    print(f"Successfully deleted directory: {dirname}")
                else:
                    error_messages.append(f"Directory '{dirname}' not found")
            except Exception as e:
                error_messages.append(f"Error deleting directory '{dirname}': {str(e)}")

        # Show results
        if error_messages:
            messagebox.showerror("Deletion Errors", 
                               f"Successfully deleted {success_count} item(s).\n\n{len(error_messages)} item(s) had errors.")
        else:
            if success_count > 0:
                print(f"Successfully deleted {success_count} items permanently.")

        # Clear selection and refresh
        self.clear_selection()
        self.refresh_content()
        self.refresh_directory_tree()

    def delete_permanently_selected_directory(self):
        """Permanently delete selected directory(ies) from trash - SIMPLIFIED CONFIRMATION"""
        if not self.current_directory:
            return

        if self.current_directory.name != "Trash":
            messagebox.showerror("Error", "Can only permanently delete directories from Trash.")
            return

        # Handle multiple selection - GET ALL SELECTED DIRECTORIES
        if len(self.selected_items) > 1:
            # Get ALL directory names that exist in current directory
            dir_names = []
            for item_name in self.selected_items:
                # Check if this item is actually a directory in the current directory
                if any(d.name == item_name for d in self.current_directory.subdirectories):
                    dir_names.append(item_name)

            if not dir_names:
                messagebox.showerror("Error", "No directories selected for deletion.")
                return

            # SIMPLIFIED confirmation - NO DIRECTORY LIST
            result = messagebox.askyesno("Confirm Permanent Delete", 
                                       f"Are you sure you want to permanently delete {len(dir_names)} directory(ies) and all their contents?\n\nThis action cannot be undone!")
            if not result:
                return

            # Delete each selected directory - CREATE A COPY OF THE LIST TO AVOID MODIFICATION DURING ITERATION
            dirs_to_delete = dir_names.copy()
            success_count = 0
            error_messages = []

            for dirname in dirs_to_delete:
                try:
                    # Find the directory object
                    dir_to_delete = None
                    for d in self.current_directory.subdirectories:
                        if d.name == dirname:
                            dir_to_delete = d
                            break
                        
                    if dir_to_delete:
                        # Remove from the subdirectories list
                        self.current_directory.subdirectories.remove(dir_to_delete)
                        success_count += 1
                        print(f"Successfully deleted directory: {dirname}")
                    else:
                        error_messages.append(f"Directory '{dirname}' not found")
                except Exception as e:
                    error_messages.append(f"Error deleting '{dirname}': {str(e)}")

            # Show results - SIMPLIFIED
            if error_messages:
                messagebox.showerror("Deletion Errors", 
                                   f"Successfully deleted {success_count} directory(ies).\n\n{len(error_messages)} directory(ies) had errors.")

            # Clear selection after deletion
            self.clear_selection()
            self.refresh_content()
            self.refresh_directory_tree()
            return

        # Handle single selection
        if not self.selected_item:
            messagebox.showerror("Error", "No directory selected for deletion.")
            return

        result = messagebox.askyesno("Confirm Permanent Delete", 
                                   f"Are you sure you want to permanently delete '{self.selected_item}' and all its contents?\nThis action cannot be undone!")
        if not result:
            return

        # Delete single directory
        try:
            dir_to_delete = None
            for d in self.current_directory.subdirectories:
                if d.name == self.selected_item:
                    dir_to_delete = d
                    break
                
            if dir_to_delete:
                self.current_directory.subdirectories.remove(dir_to_delete)
            else:
                messagebox.showerror("Error", f"Directory '{self.selected_item}' not found.")
        except Exception as e:
            messagebox.showerror("Error", f"Error deleting directory: {str(e)}")

        self.refresh_content()
        self.refresh_directory_tree()

    def empty_trash(self):
        if self.selected_item == "Trash" or (self.current_directory and self.current_directory.name == "Trash"):
            result = messagebox.askyesno("Confirm Empty Trash", 
                                       "Are you sure you want to permanently delete all files and directories in Trash?\nThis action cannot be undone!")
            if not result:
                return
            msg = trash_dir.empty_trash()
            # No success dialog - just refresh
            self.refresh_content()
            self.refresh_directory_tree()  # Refresh tree structure
        else:
            messagebox.showerror("Error", "Select Trash directory first.")

    def toggle_left_panel(self):
        """Toggle the visibility of the left panel"""
        # For static layout, this could hide/show the left frame
        # Implementation would depend on how you want to handle panel toggling
        pass

    def custom_minimize(self):
        """Custom minimize effect with fade-out animation"""
        try:
            # Save current window state
            original_alpha = self.master.attributes('-alpha')
            
            # Fade-out animation
            for alpha in [0.8, 0.6, 0.4, 0.2, 0.0]:
                self.master.attributes('-alpha', alpha)
                self.master.update()
                self.master.after(50)  # 50ms delay between steps
            
            # Actually minimize the window
            self.master.iconify()
            
            # Restore alpha for when window is restored
            self.master.attributes('-alpha', original_alpha)
            
        except Exception as e:
            print(f"Custom minimize error: {e}")
            # Fallback to normal minimize
            self.master.iconify()

    def refresh_all(self):
        self.refresh_directory_tree()
        self.refresh_content()

    def auto_save(self):
        """Auto-save without user dialogs"""
        try:
            save_file_system()
        except Exception as e:
            print(f"Auto-save failed: {e}")
    
    def setup_auto_save(self):
        """Set up automatic saving every 5 minutes"""
        def auto_save_timer():
            if self.master.winfo_exists():
                self.auto_save()
                # Schedule next auto-save
                self.master.after(300000, auto_save_timer)  # 300000 ms = 5 minutes

        # Start the auto-save timer
        self.master.after(300000, auto_save_timer)  # First save after 5 minutes

    def on_close(self):
        """Handle application close - save silently without dialogs"""
        try:
            # Save silently without showing any dialogs
            save_file_system()
        except Exception as e:
            # Only print error to console, don't show dialogs during close
            print(f"Warning: Could not save state during close: {e}")
    
        # Destroy the window
        self.master.destroy()

    def update_role_display(self):
        """Update the role display in the dropdown and icon"""
        role_display = "ADMIN" if current_user["role"] == UserRole.ADMIN else "USER"
        self.user_var.set(f"{current_user['username']} ({role_display})")

        # Update icon
        icon_to_use = None
        if current_user["role"] == UserRole.ADMIN:
            icon_to_use = self.admin_icon if self.admin_icon else None
        else:
            icon_to_use = self.user_icon if self.user_icon else None

        if icon_to_use:
            self.user_icon_label.config(image=icon_to_use)

# Run app
if __name__ == "__main__":
    root_tk = tk.Tk()
    app = FileSystemApp(root_tk)
    root_tk.mainloop()