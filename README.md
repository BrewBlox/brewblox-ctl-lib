# brewblox-ctl dynamic library

[brewblox-ctl](https://github.com/BrewBlox/brewblox-ctl) is the CLI tool for installing and managing BrewBlox. It is installed through Pip.

The problem is that Pip only ever has a single "latest" version, and BrewBlox can have multiple: one for each release track. There can also be multiple BrewBlox installations on the same host.

The chosen solution is to have a common core of functionality in the `brewblox-ctl` package, and import anything specific to the release or the install from a locally deployed python code directory.

This can satisfy use cases where:
- `brewblox-one` is using the `edge` release track, and `brewblox-two` is using `develop`
- `brewblox-one` is one or more releases ahead of `brewblox-two`

If we add the current directory to the search path, we can resolve an import of `brewblox_ctl_lib` at runtime.

Example file structure:
```
.
|-- brewblox-one/
|   |-- brewblox_ctl_lib/
|   |-- couchdb/
|   |-- influxdb/
|   |-- traefik/
|   |-- .env
|   `-- docker-compose.yml
|
`-- brewblox-two/
    |-- brewblox_ctl_lib/
    |-- couchdb/
    |-- influxdb/
    |-- traefik/
    |-- .env
    `-- docker-compose.yml
```

To avoid needlessly tight coupling between `brewblox_ctl` and `brewblox_ctl_lib`, the interface is defined as follows:

```python
# brewblox_ctl_lib/loader.py

def cli_sources() -> List[click.Group]:
    ...
```

## Deployment

BrewBlox as a whole makes extensive use of Docker. This is not directly recommended as a versioning/deployment mechanism for raw files, but there is no reason why we shouldn't use it like that anyway.

We deploy the `brewblox/brewblox-ctl-lib` docker image, that inherits from `scratch`, and just contains the `/brewblox_ctl_lib` directory.

This way we keep our deployment mechanism consistent with the rest of the software, but avoid needless overhead in the image.

As it does not contain executable code, we also don't need to have separate Docker images for AMD/ARM.

## Development

`./dev/` and `./brewblox/` are added to `.gitignore`. To create a dev environment, run the following commands:

```
brewblox-ctl install
cd brewblox
bash ../dev-deploy.sh
```

Re-run `../dev-deploy.sh` any time you want to test new changes in a `brewblox-ctl` CLI context.