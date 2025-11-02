"""
Interactive QCOW2 Image Builder with optional Dry Run mode.
"""
import os
import sys
import shutil
from datetime import datetime
import curses

# === Configuration ===
IMAGE_SIZE = '32G'
DOWNLOAD_DIR = os.path.abspath('./download')
OUTPUT_DIR = os.path.abspath('./output')
WORKDIR_BASE = '/dev/shm/build'

BASE_IMAGE_URLS = {
    'debian-13': 'https://cdimage.debian.org/images/cloud/trixie/latest/debian-13-genericcloud-amd64.qcow2',
    'ubuntu-2204': 'https://cloud-images.ubuntu.com/jammy/current/jammy-server-cloudimg-amd64.img',
}

# Global dry run flag
DRY_RUN = '--dry-run' in sys.argv

def run_cmd(cmd):
    if DRY_RUN:
        print(f"[Dry Run] $ {' '.join(cmd)}")
    else:
        print(f"$ {' '.join(cmd)}")
        os.system(' '.join(cmd))

def tui_single_select(prompt, options):
    selected = 0
    def curses_main(stdscr):
        nonlocal selected
        curses.curs_set(0) # 隐藏光标
        while True:
            stdscr.clear()
            stdscr.addstr(0, 0, prompt)
            for i, opt in enumerate(options):
                prefix = "> " if i == selected else "  "
                style = curses.A_REVERSE if i == selected else curses.A_NORMAL
                stdscr.addstr(i + 2, 0, f"{prefix}{opt}", style)
            key = stdscr.getch()
            if key == curses.KEY_UP and selected > 0:
                selected -= 1
            elif key == curses.KEY_DOWN and selected < len(options) - 1:
                selected += 1
            elif key in [10, 13]:
                break
    curses.wrapper(curses_main)
    return options[selected]

def tui_ordered_multi_select(options):
    selected = []
    current = 0

    def curses_main(stdscr):
        nonlocal current
        curses.curs_set(0)
        while True:
            stdscr.clear()
            stdscr.addstr(
                0, 0,
                "↑↓ 移动, 空格 选/取消, 回车 确认"
            )
            for i, opt in enumerate(options):
                if opt in selected:
                    prefix = f"[{selected.index(opt)+1}]"
                else:
                    prefix = "[ ]"
                line = f"{prefix} {opt}"
                style = curses.A_REVERSE if i == current else curses.A_NORMAL
                stdscr.addstr(i + 2, 0, line, style)

            key = stdscr.getch()
            if key == curses.KEY_UP and current > 0:
                current -= 1
            elif key == curses.KEY_DOWN and current < len(options) - 1:
                current += 1
            elif key == ord(' '):
                # 切换选中状态
                if options[current] in selected:
                    selected.remove(options[current])
                else:
                    selected.append(options[current])
            elif key in [10, 13]:  # Enter
                break
    curses.wrapper(curses_main)
    return selected

def main():
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')

    # OS selection
    os_tag = tui_single_select("Select target OS:", list(BASE_IMAGE_URLS.keys()))
    base_url = BASE_IMAGE_URLS[os_tag]
    base_name = os.path.basename(base_url)
    base_path = os.path.join(DOWNLOAD_DIR, base_name)
    script_dir = os.path.join('script', os_tag)

    # Validate script files
    base_script = os.path.join(script_dir, 'base')
    clean_script = os.path.join(script_dir, 'clean')
    if not os.path.isfile(base_script):
        sys.exit(f"Missing script: {base_script}")
    if not os.path.isfile(clean_script):
        sys.exit(f"Missing script: {clean_script}")

    # Choose customization scripts
    all_scripts = sorted(
        f for f in os.listdir(script_dir)
        if os.path.isfile(os.path.join(script_dir, f)) and f not in ['base', 'clean']
    )
    middle_scripts = tui_ordered_multi_select(all_scripts) if all_scripts else []
    scripts = ['base'] + middle_scripts + ['clean']

    # Prepare directories
    os.makedirs(DOWNLOAD_DIR, exist_ok=True)
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    workdir = os.path.join(WORKDIR_BASE, timestamp)
    os.makedirs(workdir, exist_ok=True)

    # Download if needed
    if not os.path.exists(base_path):
        run_cmd(["axel", base_url ,'-o', base_path])
    else:
        print(f"Using existing image: {base_path}")

    # Image paths
    image_path = os.path.join(workdir, f"{timestamp}.img")
    compressed_path = os.path.join(workdir, f"{timestamp}-compressed.img")

    # Build and customize
    run_cmd(['qemu-img', 'create', '-f', 'qcow2', image_path, IMAGE_SIZE])
    run_cmd(['virt-resize', '--expand', '/dev/sda1', base_path, image_path])
    customize_cmd = ['virt-customize', '-a', image_path]
    for s in scripts:
        customize_cmd += ['--commands-from-file', os.path.join(script_dir, s)]
    run_cmd(customize_cmd)

    # Compress
    run_cmd(['virt-sparsify', '--compress', '--tmp', '/dev/shm/', image_path, compressed_path])

    # Final file name
    tag = os_tag + ('-' + '-'.join(middle_scripts) if middle_scripts else '')
    final_img = f"{tag}-{timestamp}.img"
    final_dest = os.path.join(OUTPUT_DIR, final_img)
    run_cmd(['cp', compressed_path, final_dest])
    run_cmd(['rm', '-rf', workdir])
    print(f"\nFinal image ready at: {final_dest}")

if __name__ == '__main__':
    main()

