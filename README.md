# Farbod AI-Hub — Latest release: 28.2.4 Mac Final

The latest complete application is provided in **[Farbod_AI-Hub_v28.2.4_Mac_Final.zip](Farbod_AI-Hub_v28.2.4_Mac_Final.zip)**. Open the archive above and choose **Download raw file** to download it.

**Use the versioned ZIP for installation.** The loose source files in the repository root are retained from the earlier source edition; they have not been upgraded to 28.2.4. GitHub's green **Code → Download ZIP** downloads the entire repository, including those historical files, rather than just the current application package.

## Start on macOS

1. Install and start Docker Desktop.
2. Extract `Farbod_AI-Hub_v28.2.4_Mac_Final.zip`.
3. Open Terminal in the extracted application folder and run `bash DOCKER_START.command`.
4. Open `https://localhost`.

The first build needs internet access to public image and package sources. This is a source package, not a signed macOS `.app` or DMG. Local Ollama defaults to `http://host.docker.internal:11434`; model weights are not bundled.

## Upgrade an existing installation

Back up first. Preserve `.env.docker` and `docker-data/`, overlay the extracted application files into the existing installation, and run `bash DOCKER_UPDATE.command`. Existing custom image references and data paths are retained.

## Included in 28.2.4

- Farbod branding and the original logo.
- Independent Linux Health Command Library: searchable built-in/custom commands, full script editing, and no default-selected commands.
- 1–256 network/SAN ports; eight FC and eight Ethernet ports per named ICB.
- Optional warehouse identifiers with duplicate detection, atomic bulk issues, mandatory movement dates, and filtered Excel reports.
- Five themes and the existing asset, equipment, automation, and knowledge features.

## Validation and provenance

The archive is the original 28.2.4 Mac Final package, without application changes. Python syntax (67 files), shell syntax (48 scripts), and ZIP integrity checks passed during publication preparation. A selected test run passed 19 tests and failed two existing tests in `tests/test_linux_health_integration.py`: missing database tables in the test setup and an expected HTTP 401 versus actual 422 response. Native macOS Docker Desktop execution and live hardware integration were not tested in this environment.

The release includes configuration examples, not local databases, deployment secret files, or runtime data. See the package's release and validation notes for its earlier validation record.

SHA-256 of the release ZIP:

```text
61380ff7d4af454eb88d1cd241cc54cc1820f2fdacf02dfc408f947334bd2290
```

## Earlier versions

The v26.1.4 archive and earlier source history remain available in this repository.
