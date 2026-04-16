import sys, os

with open('/tmp/mfv-diag9.txt', 'w') as f:
    f.write(f"CWD: {os.getcwd()}\n")
    
    # Test venv access
    tests = [
        '/Users/duwanshu/Desktop/xiaohongshu-skills-main/.venv/lib/python3.11/site-packages/markupsafe/__init__.py',
        '/Users/duwanshu/Desktop/xiaohongshu-skills-main/.venv/pyvenv.cfg',
        '/Users/duwanshu/Desktop/xiaohongshu-skills-main/webapp/server.py',
    ]
    
    for path in tests:
        try:
            with open(path, 'r') as tf:
                tf.read(10)
            f.write(f"OK: {os.path.basename(path)}\n")
        except Exception as e:
            f.write(f"FAIL: {os.path.basename(path)}: {e}\n")
    
    # Now test import with PYTHONPATH
    f.write(f"PYTHONPATH: {os.environ.get('PYTHONPATH', 'NOT SET')}\n")
    try:
        import markupsafe
        f.write(f"markupsafe import OK: {markupsafe.__version__}\n")
    except Exception as e:
        f.write(f"markupsafe import FAIL: {e}\n")
    
    f.write("Done\n")
