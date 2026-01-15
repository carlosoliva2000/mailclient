# mailpy
A Python script to read, reply and write emails, provided with templates and actions to execute when reading emails.

To execute from CLI (without installation):

```
python3 -m mailpy.main
```

To create a executable with pyinstaller:

```
pyinstaller \
  --clean \
  --onefile \
  --name mailpy \
  mailpy/main.py
```
