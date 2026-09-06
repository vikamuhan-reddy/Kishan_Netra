// ---------------------------------------------------------------------------
// Smart Farming Assistant - Tier 1 sensor node enclosure
// SIH PS 26180 / Qualcomm
//
// Parametric IP65-intent field enclosure for one ESP32 + LoRa sensor node.
//
// Houses:  ESP32 LoRa SX1278 board with OLED, 18650 cell + holder,
//          TP4056 charge module, SMA antenna bulkhead.
// Ports:   2x PG7 cable glands (soil probe, solar panel) on the UNDERSIDE,
//          1x SMA antenna on the side wall.
// Mounts:  zip-tie slots on the rear for pole mounting,
//          solar panel bosses on the lid.
//
// Render a single part from the command line:
//   openscad -o base.stl -D 'part="base"' sensor_node_enclosure.scad
//
// Design notes that matter for the field, not just for printing:
//  - Glands point DOWN. Water runs off rather than sitting on a seal.
//  - The lid overhangs the base to shed rain away from the seam.
//  - The gasket groove takes 2 mm silicone O-ring cord, which is the
//    realistic route to IP65 on a printed part. Printed plastic alone
//    is not a seal, and we do not claim IP65 until it is tested.
// ---------------------------------------------------------------------------

part = "assembly";  // "base" | "lid" | "bracket" | "assembly" | "exploded"

/* [Internal volume] */
inner_l = 90;    // along the battery
inner_w = 70;
inner_h = 45;

/* [Shell] */
wall      = 2.5;
floor_t   = 3.0;
corner_r  = 4.0;
lid_t     = 3.0;
lid_lip   = 2.0;  // how far the lid overhangs the base, to shed water

/* [Seal] */
gasket_cord   = 2.0;   // silicone O-ring cord diameter
gasket_groove = 1.4;   // groove depth; cord stands proud and compresses

/* [Fasteners] */
boss_od     = 7.0;
boss_id     = 2.6;     // M3 self-tapping
boss_inset  = 7.0;

/* [Ports] */
gland_d     = 12.5;    // PG7 cable gland
gland_pitch = 30;
sma_d       = 6.5;     // SMA bulkhead

/* [Components - datasheet nominal, confirm against parts on hand] */
esp_l = 65; esp_w = 27; esp_h = 12;
bat_l = 76; bat_w = 21; bat_h = 20;
tp_l  = 26; tp_w  = 17; tp_h  = 5;

/* [Solar panel - 6V 2W] */
// The panel (110 x 70) is LARGER than the lid (95 x 75), so it cannot bolt
// flat to the lid. It also should not: a horizontal panel in an Indian field
// collects dust and standing water and loses most of its output within weeks.
// It mounts instead on a tilted bracket, facing south at roughly the site
// latitude, so rain sheds and washes the surface.
panel_l = 110; panel_w = 70;
panel_tilt = 22;              // degrees; ~site latitude for central India
panel_boss_pitch_l = 60;      // bracket feet, kept clear of the corner bosses
panel_boss_pitch_w = 40;

$fn = 48;

outer_l = inner_l + 2 * wall;
outer_w = inner_w + 2 * wall;

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

module rounded_box(l, w, h, r) {
    hull()
        for (x = [r, l - r], y = [r, w - r])
            translate([x, y, 0]) cylinder(r = r, h = h);
}

module screw_bosses(h, id) {
    for (x = [boss_inset, outer_l - boss_inset],
         y = [boss_inset, outer_w - boss_inset])
        translate([x, y, 0])
            difference() {
                cylinder(d = boss_od, h = h);
                translate([0, 0, -0.1]) cylinder(d = id, h = h + 0.2);
            }
}

// ---------------------------------------------------------------------------
// Base
// ---------------------------------------------------------------------------

module base() {
    total_h = floor_t + inner_h;

    difference() {
        union() {
            rounded_box(outer_l, outer_w, total_h, corner_r);
            // rear pole-mount bracket
            translate([0, outer_w, 0]) rear_bracket();
        }

        // cavity
        translate([wall, wall, floor_t])
            rounded_box(inner_l, inner_w, inner_h + 1, max(corner_r - wall, 1));

        // gasket groove in the top rim
        translate([wall / 2, wall / 2, total_h - gasket_groove])
            difference() {
                rounded_box(outer_l - wall, outer_w - wall,
                            gasket_groove + 0.1, corner_r);
                translate([gasket_cord, gasket_cord, -0.1])
                    rounded_box(outer_l - wall - 2 * gasket_cord,
                                outer_w - wall - 2 * gasket_cord,
                                gasket_groove + 0.3, max(corner_r - 2, 0.5));
            }

        // cable glands, underside, pointing down
        for (i = [0, 1])
            translate([outer_l / 2 - gland_pitch / 2 + i * gland_pitch,
                       outer_w / 2, -0.1])
                cylinder(d = gland_d, h = floor_t + 0.2);

        // SMA antenna bulkhead, side wall, high up and away from the glands
        translate([outer_l - 18, -0.1, floor_t + inner_h - 12])
            rotate([-90, 0, 0]) cylinder(d = sma_d, h = wall + 0.2);
    }

    // internal standoffs and fastener bosses
    translate([0, 0, floor_t]) screw_bosses(inner_h, boss_id);
    translate([0, 0, floor_t]) standoffs();
}

module standoffs() {
    // 18650 holder sits on the floor along the long axis
    for (x = [wall + 6, wall + 6 + bat_l - 10])
        translate([x, wall + 8, 0]) cylinder(d = 6, h = 3);

    // ESP32 board on posts above the cell
    for (x = [wall + 8, wall + 8 + esp_l - 8])
        for (y = [wall + 34, wall + 34 + esp_w - 8])
            translate([x, y, 0])
                difference() {
                    cylinder(d = 6, h = bat_h + 4);
                    translate([0, 0, bat_h - 2]) cylinder(d = 2.2, h = 7);
                }
}

module rear_bracket() {
    // Two zip-tie slots. Zip ties beat a U-bolt here: a farmer can
    // re-site the node with no tools, and there is nothing to rust.
    slot_w = 4; slot_h = 10; plate_t = 4;
    difference() {
        translate([corner_r, 0, 0])
            cube([outer_l - 2 * corner_r, plate_t, floor_t + inner_h]);
        for (z = [12, floor_t + inner_h - 18])
            for (x = [outer_l / 2 - 22, outer_l / 2 + 18])
                translate([x, -0.1, z]) cube([slot_w, plate_t + 0.2, slot_h]);
    }
}

// ---------------------------------------------------------------------------
// Lid
// ---------------------------------------------------------------------------

module lid() {
    lip_l = outer_l + 2 * lid_lip;
    lip_w = outer_w + 2 * lid_lip;

    difference() {
        union() {
            // top plate with a rain-shedding overhang
            rounded_box(lip_l, lip_w, lid_t, corner_r + lid_lip);
            // skirt that drops over the base
            translate([lid_lip, lid_lip, -3])
                difference() {
                    rounded_box(outer_l, outer_w, 3, corner_r);
                    translate([wall, wall, -0.1])
                        rounded_box(inner_l, inner_w, 3.2,
                                    max(corner_r - wall, 1));
                }
            // solar panel bosses
            translate([lid_lip, lid_lip, lid_t]) panel_bosses();
        }

        // fastener clearance holes
        translate([lid_lip, lid_lip, -3.1])
            for (x = [boss_inset, outer_l - boss_inset],
                 y = [boss_inset, outer_w - boss_inset])
                translate([x, y, 0]) cylinder(d = 3.4, h = lid_t + 4);

        // countersinks
        translate([lid_lip, lid_lip, lid_t - 1.6])
            for (x = [boss_inset, outer_l - boss_inset],
                 y = [boss_inset, outer_w - boss_inset])
                translate([x, y, 0]) cylinder(d1 = 3.4, d2 = 6.4, h = 1.7);
    }
}

module panel_bosses() {
    for (x = [outer_l / 2 - panel_boss_pitch_l / 2,
              outer_l / 2 + panel_boss_pitch_l / 2],
         y = [outer_w / 2 - panel_boss_pitch_w / 2,
              outer_w / 2 + panel_boss_pitch_w / 2])
        translate([x, y, 0])
            difference() {
                cylinder(d = 7, h = 5);
                translate([0, 0, 1]) cylinder(d = 2.6, h = 5);
            }
}

// ---------------------------------------------------------------------------
// Solar bracket - tilts the panel south so rain sheds and washes it
// ---------------------------------------------------------------------------

// A wedge, not a rotated plate. Two right-triangle side rails sit flat on the
// lid and carry the panel tray on their hypotenuse, so nothing dips below the
// lid and the whole thing prints without support.
module solar_bracket() {
    rail_t = 4;
    run    = panel_l * cos(panel_tilt);
    rise   = panel_l * sin(panel_tilt);
    base_x = outer_l / 2 - run / 2;
    y0     = outer_w / 2 - panel_w / 2;

    // triangular side rails
    for (y = [y0, y0 + panel_w - rail_t])
        translate([base_x, y + rail_t, 0])
            rotate([90, 0, 0])
                linear_extrude(height = rail_t)
                    polygon([[0, 0], [run, 0], [run, rise]]);

    // panel tray riding the hypotenuse
    translate([base_x, y0, 0])
        rotate([0, -panel_tilt, 0])
            difference() {
                cube([panel_l, panel_w, rail_t]);
                // open centre: sheds grit, saves filament, saves weight
                translate([10, 10, -0.1])
                    cube([panel_l - 20, panel_w - 20, rail_t + 0.2]);
            }

    // bolt pads matching the lid bosses
    for (x = [outer_l / 2 - panel_boss_pitch_l / 2,
              outer_l / 2 + panel_boss_pitch_l / 2],
         y = [outer_w / 2 - panel_boss_pitch_w / 2,
              outer_w / 2 + panel_boss_pitch_w / 2])
        translate([x, y, 0])
            difference() {
                cylinder(d = 10, h = 4);
                translate([0, 0, -0.1]) cylinder(d = 3.4, h = 4.2);
            }

    // The panel itself, visualization only. The % modifier keeps it out of
    // STL export, so this cannot contaminate a printable file.
    %translate([base_x, y0, 0])
        rotate([0, -panel_tilt, 0])
            translate([0, 0, rail_t]) cube([panel_l, panel_w, 3]);
}

// The complete sealed node as it stands in the field. Exposed as a module so
// the field-scene assembly can reuse it without redeclaring any dimension.
module full_node() {
    base();
    translate([-lid_lip, -lid_lip, floor_t + inner_h + 3]) lid();
    translate([0, 0, floor_t + inner_h + 3 + lid_t]) solar_bracket();
}

// Overall footprint, so callers can position the node without guessing.
function node_size() = [outer_l, outer_w + 4, floor_t + inner_h + 3 + lid_t];

// ---------------------------------------------------------------------------
// Views
// ---------------------------------------------------------------------------

module ghost_components() {
    %translate([wall + 6, wall + 6, floor_t + 3]) cube([bat_l, bat_w, bat_h]);
    %translate([wall + 8, wall + 32, floor_t + bat_h + 6]) cube([esp_l, esp_w, esp_h]);
    %translate([wall + 8, wall + 6, floor_t + bat_h + 6]) cube([tp_l, tp_w, tp_h]);
}

if (part == "base") base();
else if (part == "lid") lid();
else if (part == "bracket") rear_bracket();
else if (part == "solar") solar_bracket();
else if (part == "field") full_node();
else if (part == "exploded") {
    base();
    ghost_components();
    translate([-lid_lip, -lid_lip, floor_t + inner_h + 30]) lid();
} else {
    base();
    ghost_components();
    translate([-lid_lip, -lid_lip, floor_t + inner_h + 3]) lid();
}
