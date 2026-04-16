import sys, os

with open('/tmp/mfv-access.txt', 'w') as f:
    # Dump env
    for k, v in sorted(os.environ.items()):
        f.write(f"{k}={v}\n")
    f.write("---\n")
    
    # Test same file as test10
    try:
        with open('/Users/duwanshu/Desktop/xiaohongshu-skills-main/webapp/server.py', 'r') as tf:
            tf.read(5)
        f.write("server.py OK\n")
    except Exception as e:
        f.write(f"server.py FAIL: {e}\n")
    
    f.write("Done\n")
