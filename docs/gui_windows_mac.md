# La GUI en Windows y macOS

Las herramientas (LibreLane, OpenROAD) corren en un contenedor Linux, y su
interfaz gráfica se dibuja con **X11**: el programa del contenedor le pide a
un *servidor X* que abra la ventana. En Ubuntu el servidor X es el propio
escritorio, y `make gui` funciona tal cual (sección 1.2 del `README.md`). En
Windows y macOS hace falta un servidor X y decirle al contenedor cómo llegar a
él.

Esto solo hace falta para `make gui` y `make gui-footprint`. Todo lo demás
(`make footprint`, `make floorplan`, `make place`, los reportes) funciona sin
GUI.

| Sistema | Servidor X | Cómo llega el contenedor |
| :------ | :--------- | :----------------------- |
| Ubuntu | el escritorio | socket de X11 (`/tmp/.X11-unix`), automático |
| Windows | WSLg (viene con WSL2) | socket de X11, igual que en Ubuntu |
| macOS | XQuartz | TCP, con `GUI_DISPLAY=host.docker.internal:0` |

---

## Windows: WSL2 con WSLg

En Windows se trabaja **dentro de Ubuntu en WSL2** (el subsistema de Linux de
Windows). WSL2 trae **WSLg**, un servidor X ya integrado: las ventanas de
Linux aparecen como ventanas normales de Windows, sin instalar nada más.

### Instalación

1. Hace falta **Windows 11**, o **Windows 10** actualizado. En una
   PowerShell como administrador:

   ```powershell
   wsl --install -d Ubuntu-24.04
   wsl --update
   ```

   Reiniciá si te lo pide, abrí **Ubuntu** desde el menú Inicio y creá tu
   usuario.

2. **Todo lo que sigue se hace en la terminal de Ubuntu**, no en
   PowerShell. Seguí las instrucciones de instalación del `README.md` del
   TP1 tal cual, como si fuera un Ubuntu común: `docker.io`, `git`, `make`,
   el grupo `docker`, el PDK. Para que el grupo `docker` tenga efecto, cerrá
   la terminal de Ubuntu, corré `wsl --shutdown` en PowerShell y volvé a
   abrirla.

3. Cloná los repositorios **dentro del sistema de archivos de Ubuntu** (por
   ejemplo en `~/up/`), no en `/mnt/c/...`. Desde `/mnt/c` todo es mucho
   más lento y aparecen problemas de permisos.

   Si ya usás **Docker Desktop** con la integración de WSL, en vez de
   `docker.io` dentro de Ubuntu, también debería funcionar. Estas
   instrucciones suponen `docker.io`.

### Verificar y usar la GUI

En la terminal de Ubuntu:

```bash
echo $DISPLAY                          # tiene que imprimir :0
ls -la /tmp/.X11-unix/                 # tiene que aparecer X0
sudo apt install -y x11-xserver-utils  # para xhost
make gui-footprint                     # o make gui
```

La ventana de OpenROAD aparece como una ventana más de Windows.

### Si no anda

| Problema | Solución |
| :------- | :------- |
| `DISPLAY is not set` | WSLg no está activo: corré `wsl --update` y `wsl --shutdown` en PowerShell, y volvé a abrir Ubuntu |
| `/tmp/.X11-unix` está vacío o no existe | Algunas versiones borran el socket al arrancar. Recrealo: `sudo rm -rf /tmp/.X11-unix && sudo ln -s /mnt/wslg/.X11-unix /tmp/.X11-unix` |
| `could not connect to display` | Revisá lo anterior; si sigue, `wsl --shutdown` en PowerShell y volvé a abrir Ubuntu |
| Todo anda muy lento | Fijate que el repositorio esté en `~/...` y no en `/mnt/c/...` |

---

## macOS: XQuartz y Docker Desktop

En macOS el servidor X es **XQuartz**. El contenedor corre en la máquina
virtual de Docker Desktop y no puede usar el socket de X11 de la Mac, así
que se conecta a XQuartz **por TCP**, a la dirección
`host.docker.internal:0`. Esa dirección se le pasa con la variable
`GUI_DISPLAY`.

### Instalación

1. Las herramientas del TP1:
   - [Docker Desktop](https://www.docker.com/products/docker-desktop/) para
     Mac. Sirve tanto para Apple Silicon como para Intel: la imagen de
     LibreLane tiene versión para las dos.
   - `git` y `make`, con `xcode-select --install`.

   Los comandos del `README.md` del TP1 (`make pdk`, `make synth`, etc.)
   funcionan igual. En **Settings → Resources** de Docker Desktop dale
   bastante memoria: con poca, el placement puede fallar o tardar mucho.

2. XQuartz:

   ```bash
   brew install --cask xquartz      # o descargalo de https://www.xquartz.org
   ```

   Después de instalarlo, **cerrá la sesión de macOS y volvé a entrar**.

3. Abrí XQuartz y, en **XQuartz → Settings → Security**, marcá **Allow
   connections from network clients**. **Cerrá XQuartz por completo**
   (⌘Q) y volvé a abrirlo: la opción recién se aplica al reiniciarlo.

### Usar la GUI

Cada vez que vayas a usar la GUI, con XQuartz abierto, en una terminal:

```bash
xhost +localhost                          # autoriza las conexiones locales
export GUI_DISPLAY=host.docker.internal:0
make gui-footprint                        # o make gui
```

- `xhost +localhost` autoriza a cualquier programa de tu Mac a abrir
  ventanas en XQuartz. Hace falta una vez por cada vez que abrís XQuartz.
  Para revocarlo: `xhost -localhost`.
- Para no repetir el `export`, agregalo a `~/.zshrc`.
- Con `GUI_DISPLAY` definida, `run.sh` le pasa esa dirección al contenedor
  como `DISPLAY`, en vez de compartir el socket de X11 como en Linux. Ver
  `run.sh` y el target `gui` del `Makefile`.

### Si no anda

| Problema | Solución |
| :------- | :------- |
| `xhost: command not found` | Cerrá y volvé a abrir la terminal (XQuartz agrega `/opt/X11/bin` al `PATH`), o usá `/opt/X11/bin/xhost` |
| `xhost: unable to open display` | XQuartz no está abierto: abrilo y repetí |
| `could not connect to display host.docker.internal:0` | Falta la opción *Allow connections from network clients*, o no reiniciaste XQuartz después de marcarla, o falta `xhost +localhost` |
| La ventana abre pero el layout se ve en negro o no se redibuja | Probá `defaults write org.xquartz.X11 enable_iglx -bool true` y reiniciá XQuartz |

---

## Capturas de pantalla

En cualquier sistema, la forma más simple de guardar una imagen del layout es
desde la consola Tcl de la GUI: `save_image <archivo>.png`. La imagen queda en
el directorio del proyecto (sección 5 del `README.md`).
