# TIpy-asm documentation

This branch holds only the documentation. The package lives on the
[`main` branch](https://github.com/XSamuraiCoder/TIpy-asm).

The method and command references are generated from the package's own code, so a
build needs a copy of `main` in a folder named `package`:

```bash
git clone --depth 1 --branch main https://github.com/XSamuraiCoder/TIpy-asm.git package
```

```bash
python -m pip install -r docs/requirements.txt
```

```bash
python -m sphinx -W -b html docs docs/_build/html
```

Then open `docs/_build/html/index.html`.

Pushing to this branch publishes the site to GitHub Pages. A change on `main` does not
rebuild it, so after changing the public API, push a commit here:

```bash
git commit --allow-empty -m "Rebuild docs for the latest package"
```
