import sys, os

with open('/tmp/mfv-diag10.txt', 'w') as f:
    # Print ALL environment variable names
    f.write("ENV VARS:\n")
    for k, v in sorted(os.environ.items()):
        f.write(f"  {k}={v[:80]}\n")
    
    # Test file access
    try:
        with open('/Users/duwanshu/Desktop/xiaohongshu-skills-main/webapp/server.py', 'r') as tf:
            f.write(f"server.py OK\n")
    except Exception as e:
        f.write(f"server.py FAIL: {e}\n")
    
    f.write("Done\n")
