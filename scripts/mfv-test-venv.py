import sys, os

with open('/tmp/mfv-diag-venv.txt', 'w') as f:
    f.write(f"Executable: {sys.executable}\n")
    f.write(f"CWD: {os.getcwd()}\n")
    
    # Test accessing venv files
    tests = [
        '/Users/duwanshu/Desktop/xiaohongshu-skills-main/.venv/pyvenv.cfg',
        '/Users/duwanshu/Desktop/xiaohongshu-skills-main/.venv/lib/python3.11/site-packages/flask/__init__.py',
        '/Users/duwanshu/Desktop/xiaohongshu-skills-main/webapp/server.py',
    ]
    
    for path in tests:
        try:
            with open(path, 'r') as tf:
                tf.read(5)
            f.write(f"OK: {os.path.basename(path)}\n")
        except Exception as e:
            f.write(f"FAIL: {os.path.basename(path)}: {e}\n")
    
    # Try importing flask
    try:
        import flask
        f.write(f"Flask OK: {flask.__version__}\n")
    except Exception as e:
        f.write(f"Flask FAIL: {e}\n")
    
    f.write("Done\n")
