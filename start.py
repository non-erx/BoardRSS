import subprocess
import sys
import os
import signal

ROOT = os.path.dirname(os.path.abspath(__file__))
BACKEND = os.path.join(ROOT, "backend")
FRONTEND = os.path.join(ROOT, "frontend")


def main():
    procs = []
    try:
        procs.append(subprocess.Popen(
            [sys.executable, "server.py"],
            cwd=BACKEND,
        ))

        procs.append(subprocess.Popen(
            ["npm", "run", "dev"],
            cwd=FRONTEND,
            shell=True,
        ))

        print("\n  Backend:   http://localhost:8000")
        print("  Frontend:  http://localhost:3000")
        print("  Admin:     http://localhost:3000/admin\n")

        for p in procs:
            p.wait()

    except KeyboardInterrupt:
        pass
    finally:
        for p in procs:
            try:
                p.terminate()
                p.wait(timeout=3)
            except Exception:
                p.kill()


if __name__ == "__main__":
    main()
