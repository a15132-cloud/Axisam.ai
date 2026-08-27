# Backend propio, gratis para siempre, sin los bugs de un plan gratis de PaaS

Esta es la alternativa a Render (u otro host de contenedores administrado):
un servidor Linux normal, tuyo, corriendo el mismo `Dockerfile` de
`apps/orchestrator` detrás de un proxy HTTPS automático (Caddy). Resuelve
directamente el problema que tenías con Render en su plan gratis - **el
servicio se dormía tras ~15 min sin uso y tardaba ~50s en despertar**, lo
que se sentía como "errores de conexión / lentitud constante" - porque
esta VM corre 24/7, sin dormirse nunca. No es magia "sin servidor": esta
app necesita un proceso corriendo en algún lado (el motor de geometría
`cadquery`/OpenCascade es una librería nativa pesada que no cabe en un
navegador ni en una función serverless, y la `ANTHROPIC_API_KEY` tiene que
vivir en un servidor, nunca en el navegador, o cualquiera podría robarla
e inflarte la cuenta). Lo que sí puedes tener gratis y sin las
particularidades de un PaaS es la **máquina** en la que ese proceso corre.

## Por qué Oracle Cloud "Always Free"

Es la única oferta "siempre gratis" (no una prueba de 30/90 días) que da
una VM real, completa, encendida permanentemente - no un contenedor que
se apaga por inactividad como el plan free de Render/Railway/Fly. Perfil
recomendado: una instancia **Ampere A1 (ARM), hasta 4 OCPU / 24 GB RAM**,
más 200 GB de disco - muy por encima de lo que este backend necesita. Se
pide una tarjeta solo para verificar identidad; mientras te quedes dentro
de los límites "Always Free" no se cobra nada. (Si la capacidad ARM no
está disponible en tu región en el momento de crear la VM - pasa a veces
por demanda alta - Oracle también da 2 instancias AMD x86 más pequeñas
`VM.Standard.E2.1.Micro`, 1 GB RAM cada una; funcionan igual, con menos
margen.)

Cualquier otro servidor Linux con Docker sirve igual de bien - tu propia
PC vieja, un Raspberry Pi con suficiente RAM, un VPS que ya tengas. Estos
pasos son genéricos; solo los de "crear la VM" son específicos de Oracle.

## Paso 1 — Crear la VM en Oracle Cloud

1. Crea una cuenta en https://www.oracle.com/cloud/free/ (pide tarjeta
   para verificación, no cobra si te quedas en "Always Free").
2. **Create a VM Instance** → Image: **Ubuntu 24.04** (o 22.04) → Shape:
   **Ampere (VM.Standard.A1.Flex)**, 4 OCPU / 24 GB RAM (ajustable, es el
   máximo gratis) → deja el resto por defecto → **Add SSH key** (genera un
   par nuevo o pega tu clave pública) → **Create**.
3. Copia la **Public IP** que te asigna cuando termine de aprovisionar.

### Abrir los puertos 80 y 443 (el paso que todos se saltan)

Oracle bloquea todo el tráfico entrante por defecto excepto SSH (22). Sin
esto, Caddy nunca puede completar la verificación HTTPS y el dominio no
carga - se ve exactamente como "no se pudo conectar", el mismo síntoma
que ya tenías.

1. En la consola de Oracle: tu instancia → **Subnet** (link junto a
   "Virtual cloud network") → **Security Lists** → la lista por defecto →
   **Add Ingress Rules** → agrega dos reglas, ambas con **Source CIDR
   `0.0.0.0/0`**: una con **Destination Port `80`**, otra con
   **Destination Port `443`** (protocolo TCP).
2. Ubuntu también trae su propio firewall (`iptables`) activo por defecto
   en las imágenes de Oracle - conéctate por SSH (paso siguiente) y corre:
   ```bash
   sudo iptables -I INPUT -p tcp --dport 80 -j ACCEPT
   sudo iptables -I INPUT -p tcp --dport 443 -j ACCEPT
   sudo netfilter-persistent save 2>/dev/null || true
   ```

## Paso 2 — Instalar Docker en la VM

```bash
ssh ubuntu@<tu-ip-publica>
curl -fsSL https://get.docker.com | sudo sh
sudo usermod -aG docker $USER
# cierra la sesion SSH y vuelve a entrar para que el grupo tome efecto
```

## Paso 3 — Clonar el repo y configurar

```bash
git clone https://github.com/a15132-cloud/Axisam.ai.git
cd Axisam.ai/deploy
cp .env.example .env
nano .env   # pon ANTHROPIC_API_KEY y AXISCAM_DOMAIN (ver .env.example
            # para la opcion sin dominio propio, con sslip.io)
```

## Paso 4 — Levantar todo

```bash
docker compose up -d --build
docker compose logs -f caddy   # espera a ver que consiguio el certificado (Ctrl+C para salir del log)
```

La primera vez tarda unos minutos (build de la imagen con `cadquery`).
Cuando `caddy` diga algo como `certificate obtained successfully`, prueba:

```bash
curl https://TU_DOMINIO/api/health
```

Debe responder JSON con `"status": "ok"`. Si da timeout o "connection
refused", revisa el Paso 1 (puertos 80/443) antes que cualquier otra cosa
- es la causa del 90% de estos casos.

## Paso 5 — Apuntar Vercel a este backend

Igual que con Render: en el dashboard de tu proyecto de Vercel → Settings
→ Environment Variables → agrega `VITE_API_BASE_URL` =
`https://TU_DOMINIO/api` → **Redeploy** (las env vars de Vite solo aplican
en el build siguiente, no retroactivamente).

## Mantenimiento

- **Actualizar tras un `git pull`**: `cd Axisam.ai/deploy && docker
  compose up -d --build`.
- **Ver logs**: `docker compose logs -f orchestrator`.
- **Los proyectos/archivos NO se pierden** al reiniciar el contenedor o
  la VM - viven en el volumen Docker `axiscam_data`, no en el filesystem
  del contenedor. Solo se pierden si borras ese volumen a propósito
  (`docker compose down -v` - evita el flag `-v` salvo que quieras
  borrar todo).
- **Backups**: `docker run --rm -v axiscam_data:/data -v $(pwd):/backup
  alpine tar czf /backup/axiscam-backup-$(date +%F).tar.gz -C /data .`
  cuando quieras un respaldo manual del disco.
