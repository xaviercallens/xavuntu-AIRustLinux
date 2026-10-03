# M5: RunuX on Real GCE via a Custom Boot Image — Real Progress, Real Blocker

**Status: partial. The image-creation recipe works and is documented
below for reuse. Actually booting cleanly on real GCE hardware does
not work yet, and the specific cause is identified but not fixed.**
This is an honest "I couldn't get it fully working" result, per
`AGENTS.md` §1.6 — not a failure to hide.

## What this attempted

`TPU_ACCELERATOR_IMPROVEMENT_PLAN.md`'s M5: get the already-verified
`examples/x86_64_qemu_harness` (real 64-bit long-mode boot, GRUB
Multiboot2, verified locally under QEMU in `scripts/x86_64_boot_test.sh`)
to boot on a real Google Compute Engine VM via a custom disk image,
with output captured through the serial console.

## What worked: building and importing a bootable custom GCE image

1. The same GRUB-built hybrid ISO already used for local QEMU testing
   (`grub-mkrescue`, Multiboot2, `boot_hybrid.img`) turns out to also
   be directly usable as a **raw disk image** — confirmed locally
   first, for free, before any cloud step: booting the exact same
   `.iso` file via `-hda` (IDE) instead of `-cdrom` produces identical,
   correct output. This is because `grub-mkrescue`'s hybrid image
   includes real MBR boot code, not just an El Torito CD boot catalog.
2. **A real documentation error cost real time and a real (if small)
   GCP transfer/storage cost**: `gcloud compute images create
   --source-uri` requires the tarball itself to be **gzip-compressed**
   (`.tar.gz`), contrary to an initial assumption (conflating "don't
   pre-compress the raw disk before archiving" — still true — with
   "don't compress the tar" — false). Two failed attempts (including
   padding the test disk to 10GB to test an incorrect "minimum size"
   hypothesis, which cost a real ~10GB upload before being disproven)
   preceded checking `gcloud compute images create --help` directly,
   which stated the actual requirement in one line. The size-padding
   detour is recorded here as a real process mistake, not hidden.
3. Correctly packaged (`tar --format=gnu -czf disk.raw.tar.gz disk.raw`,
   ~3.2MB compressed from ~12MB raw), uploaded to a dedicated GCS
   bucket created solely for this test, and `gcloud compute images
   create ... --architecture=X86_64` succeeded, producing a real,
   `READY` custom image from RunuX's own kernel binary.
4. A VM created from that image (`e2-micro`, no external IP needed,
   `serial-port-enable=1`) reached real firmware execution — confirmed
   by real, clean SeaBIOS output on the serial console: version
   banner, RAM size, CPU count, and correct detection of the boot disk
   as a `virtio-scsi` device (`Google`/`PersistentDisk`).

## What didn't work: garbled output right after "Booting from Hard Disk 0..."

The real captured serial console output, verbatim:

```
SeaBIOS (version 1.8.2-google)
Total RAM Size = 0x0000000040000000 = 1024 MiB
CPUs found: 2     Max CPUs supported: 2
found virtio-scsi at 0:3
virtio-scsi vendor='Google' product='PersistentDisk' rev='1' type=0 removable=0
virtio-scsi blksize=512 sectors=20971520 = 10240 MiB
drive 0x000f2610: PCHS=0/0/0 translation=lba LCHS=1024/255/63 s=20971520
Sending Seabios boot VM event.
Booting from Hard Disk 0...
EePaemaera
0200:.30=0dafb= [ (ti_d
```

Then nothing further — polled with `get-serial-port-output --start=N`
after the initial capture; no new bytes appeared, confirming this is a
stable hang/garble state, not still-in-progress boot.

**Real diagnostic step taken, not skipped**: rather than assume the
cause, reproduced with a `virtio-scsi` disk **locally**, for free,
before spending more on GCE:

```
$ qemu-system-x86_64 -drive file=runux_gce_test.iso,format=raw,if=none,id=scsi0 \
    -device virtio-scsi-pci,id=scsi -device scsi-hd,drive=scsi0 -nographic ...
SeaBIOS (version 1.16.3-debian-1.16.3-2)
Booting from Hard Disk...
GRUB [INFO] Booting RunuX x86_64 QEMU Harness (long mode)...
...
[SUCCESS] RunuX x86_64 booted successfully inside QEMU (long mode)!
```

**This booted cleanly.** Same disk image, same `virtio-scsi`
controller type, standard/mainline SeaBIOS (7.2.22's bundled
1.16.3) instead of Google's fork. This rules out `virtio-scsi` itself
as the cause and narrows the real, specific, unresolved suspect to
**Google's own SeaBIOS fork, version `1.8.2-google`** (substantially
older than the mainline `1.16.3` tested locally) — most likely a
difference in its INT13h extended-read handling for the multi-sector
reads GRUB's stage-2/`core.img` loader performs after the initial MBR
sector, though the exact mechanism was not isolated further.

## Why this stops here

Debugging Google's specific SeaBIOS fork further would require either
(a) obtaining that exact SeaBIOS binary/source to test locally (not
attempted — no confirmed source located in the time available), or (b)
further iteration cycles on real GCE, each with a real cost and
multi-minute round-trip. Given `AGENTS.md`'s explicit preference for
"I couldn't" over forcing a result, and that this is real firmware
compatibility debugging rather than a bounded, well-scoped increment,
this is recorded as a genuine stopping point rather than pushed
further in this pass.

## What this does and doesn't show

- **Does show:** a real, reusable, now-documented recipe for turning
  RunuX's existing GRUB-built boot image into a GCE custom image (the
  gzip-tarball requirement, the `--architecture=X86_64` flag, the
  `serial-port-enable=1` metadata for console capture) — genuinely new
  capability for this project, reusable once the boot issue is fixed.
  Does show SeaBIOS-level firmware execution succeeds on real GCE
  hardware for an image built from RunuX's own kernel. Does show the
  disk-controller type (`virtio-scsi`) is not the root cause, ruled
  out by a real local reproduction rather than assumed.
- **Doesn't show:** a working RunuX boot on real cloud hardware yet.
  Doesn't show the exact root cause within Google's SeaBIOS fork.
  Doesn't include any fix.

## Cost and cleanup

One dedicated GCS bucket (created and fully deleted), a small number
of `gcloud compute images create` attempts (two of which failed before
any resource was created; costs were transfer/storage only, no compute
cost — no VM ran during the image-creation failures), one `e2-micro`
VM with no external IP created and deleted within a few minutes for
the actual boot test. All resources (bucket, images, VM) confirmed
deleted via a full sweep after this work; only the two pre-existing,
unrelated resources in this project remain untouched.

## Reproduce the working parts yourself

```bash
# Build the same GRUB Multiboot2 image already verified locally:
bash scripts/x86_64_boot_test.sh   # produces the ISO this recipe reuses

# Package correctly (note: .tar.gz, not plain .tar):
cp <the built iso> disk.raw
tar --format=gnu -czf disk.raw.tar.gz disk.raw

# Upload and import:
gsutil cp disk.raw.tar.gz gs://YOUR_BUCKET/disk.raw.tar.gz
gcloud compute images create runux-x86-64-boot \
  --source-uri=gs://YOUR_BUCKET/disk.raw.tar.gz --architecture=X86_64

# Boot and capture (reproduces the garbled result until the SeaBIOS
# fork issue is fixed):
gcloud compute instances create runux-boot-test --image=runux-x86-64-boot \
  --machine-type=e2-micro --no-address --metadata=serial-port-enable=1
gcloud compute instances get-serial-port-output runux-boot-test
```

## Next steps (not started)

- Try `--guest-os-features=UEFI_COMPATIBLE` with a GPT+ESP-formatted
  disk instead of legacy BIOS boot, sidestepping Google's SeaBIOS fork
  entirely (a genuinely different, unexplored path).
- Try a `q35`-family machine type (some GCE machine families use a
  different chipset/firmware baseline) to see if the fork-specific
  behavior differs.
- File the specific garbled-output symptom as a data point if a public
  channel for Google's SeaBIOS fork issues exists (not investigated).
