# CAD — Mechanical Design

Parametric OpenSCAD source. Everything here is text, diffable and version-controlled;
nothing depends on a proprietary CAD file that only one team member can open.

**The product is a fixed, pole-mounted sentinel node.** It is installed once and left
to watch one zone of a field for a season. It does not move, and there is no mobility,
navigation or path-planning anywhere in this design. Per `ai/PS-26180-MASTER.md` §464.

## Files

| File | What it is | Printable? |
|---|---|---|
| [`product_assembly.scad`](product_assembly.scad) | **The product.** Full sentinel field station: mast, tilted 10–20 W solar panel, sealed electronics enclosure, fixed canopy-facing camera housing with sun hood, antenna, in-ground soil probes at 100 mm and 300 mm | Massing model |
| [`sensor_node_enclosure.scad`](sensor_node_enclosure.scad) | Tier-1 sensor node enclosure — ESP32 + LoRa, 18650 cell, gasket groove, PG7 cable glands, pole-mount bracket | ✅ **Yes** |

## Renders

| Image | View |
|---|---|
| `product_station.png` | Sentinel station, full height |
| `product_field.png` | Station sited in a field |
| `render_exploded.png` | Sensor enclosure, exploded |

STL files are **not** committed — they are generated output. Regenerate them with the
commands below.

## Rebuilding

```bash
OS="/c/Program Files/OpenSCAD/openscad.exe"

# Render the full station
"$OS" -o product_station.png --imgsize=1400,1050 --viewall --autocenter \
      product_assembly.scad

# Export printable parts
"$OS" -o sensor_node_base.stl    -D 'part="base"'     sensor_node_enclosure.scad
"$OS" -o sensor_node_lid.stl     -D 'part="lid"'      sensor_node_enclosure.scad
"$OS" -o sensor_node_bracket.stl -D 'part="bracket"'  sensor_node_enclosure.scad
"$OS" -o sensor_node_solar.stl   -D 'part="solar"'    sensor_node_enclosure.scad
```

`sensor_node_enclosure.scad` exposes a `part` variable
(`base` | `lid` | `bracket` | `solar` | `field` | `assembly` | `exploded`)
so a single source produces each component.

## Design decisions embedded in the geometry

These look like styling and are not:

- **Cable glands point down.** Water runs off rather than pooling on a seal.
- **Lid overhangs the base.** Sheds rain away from the gasket seam.
- **Gasket groove takes 2 mm silicone O-ring cord.** Printed plastic alone is not a seal.
  ⚠️ Designed for outdoor environmental protection. No IP rating is claimed — none has
  been tested.
- **Solar panel tilted ~22°, not flat.** A horizontal panel in an Indian field silts up
  with dust within weeks. Tilted, rain sheds and washes it.
- **Solar panel sized for monsoon overcast, not average sun.** The node has to survive
  its worst week, not its average one.
- **Camera is a sealed fixed housing, not a phone cradle.** It is aimed at the canopy
  and must survive monsoon, dust and 45 °C unattended for a season.
- **Camera sun hood.** Harsh direct sun blows out highlights and puts specular glare on
  waxy leaves — exactly the domain shift that collapses a model trained on evenly lit
  images. A hardware mitigation for a machine-learning failure, at about two rupees of
  filament. See [`docs/00_initial_technical_assessment.md`](../../docs/00_initial_technical_assessment.md) §4.
- **Two soil probes at 100 mm and 300 mm.** One reports what the surface did after
  irrigation or rain; the other reports what the root zone actually holds. A single probe
  confuses "I watered the top" with "the plant can drink" — the exact distinction the
  fusion engine depends on.
- **Pole-mounted and stationary.** One node watches one zone. Coverage is extended by
  installing more nodes, not by moving one.

## Status

⚠️ These are **design models**, not manufacturing-released drawings. The sensor node
enclosure exports clean STLs and can be printed. The station is a massing model:
dimensions are BOM-derived and the layout is sound, but fastener detail and bracket
interfaces need a detailing pass before fabrication.

No mechanical claim (sealing, load, thermal) has been tested.

> **History.** Two designs were removed rather than left to rot: a `camera_mast_mount.scad`
> holding a phone on a pole (the phone premise was withdrawn by DR-012), and a
> `hexapod_robot.scad` walking platform from a period when the design drifted toward a
> mobile robot. That drift was ended by written specification; the sentinel above is the
> design of record. Renders of both are gone with their sources.
