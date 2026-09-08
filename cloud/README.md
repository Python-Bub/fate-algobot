# Run training on Google Cloud (more RAM + disk)

Your laptop project is **~10 GB** (not 800 GB). RAM pressure comes from **16 GB RAM + parallel training**, not from “cloud storage.”

**What helps:**

| Goal | Solution |
|------|----------|
| More RAM, faster training | **Compute Engine VM** (e.g. `n2-highmem-8`: 64 GB RAM) |
| Never lose checkpoints | VM disk + `sync` back to Mac, or **GCS bucket** (`gsutil rsync`) |
| Object storage only | **Cloud Storage** — cheap archive, **does not add RAM** |

## 1) GCP signup (you do this once)

1. Open [Google Cloud Free Program](https://cloud.google.com/free/docs/free-cloud-features#free-trial).
2. Create a billing account (credit card). New accounts get **$300 free credit** for 90 days.
3. [Console](https://console.cloud.google.com) → create project e.g. `fate-algobot`.
4. Enable **Compute Engine API**: APIs & Services → Enable APIs → “Compute Engine API”.
5. Install CLI on your Mac:

   ```bash
   brew install --cask gcloud-cli
   gcloud auth login
   ```

   If `gcloud init` asks “Pick configuration”: type **`1`** (re-initialize default).
   Prefer skipping the rest of init — this repo already sets:

   ```bash
   gcloud config set project fate-algobot-demir
   gcloud config set compute/region us-central1
   gcloud config set compute/zone us-central1-a
   ```

   **Billing must be linked** or Compute VMs refuse to start:

   https://console.cloud.google.com/billing?project=fate-algobot-demir

   Then: `./cloud/gcp_bootstrap.sh setup` → `./cloud/gcp_bootstrap.sh paper`

   Do **not** paste `paper`, `up`, `sync`, and `down` on one line. `down` deletes the VM.

6. Verify:

   ```bash
   gcloud auth list
   gcloud config get-value project
   ```

## 2) Copy secrets to the VM (required for Alpaca / APIs)

From your Mac (after VM exists — run `up` first or use placeholder):

```bash
gcloud compute instances create fate-algobot-trainer --zone=us-central1-a ...   # or ./cloud/gcp_bootstrap.sh up
rsync -avz -e "gcloud compute ssh --zone=us-central1-a fate-algobot-trainer --" \
  /path/to/FATE_AlgoBot/.env fate-algobot-trainer:~/FATE_AlgoBot/.env
```

## 3) Bootstrap VM + start training

```bash
cd /path/to/FATE_AlgoBot
./cloud/gcp_bootstrap.sh up
```

Then:

| Command | Action |
|---------|--------|
| `./cloud/gcp_bootstrap.sh status` | VM state + `./run_all.sh progress` on VM |
| `./cloud/gcp_bootstrap.sh ssh` | Shell on VM (`tmux attach -t train` to see training) |
| `./cloud/gcp_bootstrap.sh sync` | Pull `models/` + checkpoints to your Mac |
| `./cloud/gcp_bootstrap.sh down` | Delete VM (stop charges) |

## 4) Optional: archive to Cloud Storage (not RAM)

```bash
gcloud storage buckets create gs://YOUR-UNIQUE-BUCKET-NAME --location=us-central1
gcloud storage rsync -r ~/FATE_AlgoBot/models gs://YOUR-UNIQUE-BUCKET-NAME/fate-models/
```

## 24/7 paper (do not use SPOT)

Laptop lid-close / DNS sleep is why execution-monitor dies overnight. Paper trading
needs a **STANDARD** VM that is not preempted:

```bash
brew install --cask gcloud-cli
gcloud init    # project + billing
./cloud/gcp_bootstrap.sh paper
```

Then: `GCP_INSTANCE=fate-algobot-paper ./cloud/gcp_bootstrap.sh ssh` → `tmux attach -t paper`.

On the VM, install reboot-safe paper once:

```bash
bash ~/FATE_AlgoBot/cloud/install_paper_systemd.sh
```

The GitHub copy of this repo is **private**. Alpaca keys stay in `.env` on the VM only — never in git.

`up` is still the **training** Spot VM. `paper` is the always-on trading box.

**Recommended spend (us-central1, Sep 2026 list):** paper n2-standard-4 STANDARD
24/7 ≈ **$162/mo** (compute $142 + 200 GB disk $20). Add Spot n2-highmem-8
~8 h/day ≈ **$40–50**. Month-1 total ≈ **$205**. Do not leave an L4 GPU on
24/7 (~$640). After paper is stable, 1-year CUD on the paper VM only (~$89
compute). See the in-editor plan canvas.

- **Spot** `n2-highmem-8` in `us-central1`: on-demand **$0.52/h**; Spot often
  ~$0.16–0.21/h (check [pricing](https://cloud.google.com/compute/all-pricing)).

## Env overrides

| Variable | Default | Meaning |
|----------|---------|---------|
| `GCP_ZONE` | `us-central1-a` | Zone |
| `GCP_MACHINE` | `n2-highmem-8` (train) / `n2-standard-4` (`paper`) | Machine type |
| `GCP_DISK_GB` | `200` | Boot disk size (paper needs room for models) |
| `GCP_INSTANCE` | `fate-algobot-trainer` / `fate-algobot-paper` | Set when SSHing to paper |
| `TRAIN_WORKERS` / `INTRADAY_WORKERS` | 8 / 4 | Set inside `gcp_remote_setup.sh` on VM |
