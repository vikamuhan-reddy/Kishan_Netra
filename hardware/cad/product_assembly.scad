// ---------------------------------------------------------------------------
// Smart Farming Assistant - AUTONOMOUS FIELD STATION, full product assembly
// SIH PS 26180 / Qualcomm
//
// Render:
//   openscad -o product.png --imgsize=1400,1050 --viewall --autocenter \
//            product_assembly.scad
//
// AUTONOMY IS THE DESIGN DRIVER
// ----------------------------
// This node is installed once and left in the field for a season. Nobody holds
// it, nobody carries a phone to it, nobody presses anything. That single
// requirement dictates almost every dimension below:
//
//   * Solar panel is sized for the WORST case (monsoon overcast), not average
//     sun, and tilted so rain washes the dust off. A flat panel silts up.
//
//   * The Snapdragon compute module is NOT always on. An always-on low-power
//     MCU watches the soil and air sensors and wakes the SoC only when a
//     capture is actually warranted. Running an application SoC continuously
//     is not solar-feasible at smallholder cost. See docs/22_power_autonomy.md.
//
//   * The camera is a sealed fixed housing aimed at the canopy, not a cradle
//     holding somebody's phone. It must survive monsoon, dust and 45 C.
//
//   * Two soil probes at different depths. One tells you what the surface is
//     doing after irrigation or rain; the other tells you what the root zone
//     actually has. A single probe confuses "I watered the top" with "the
//     plant can drink", which is exactly the distinction the fusion engine
//     depends on.
//
// This file is the visualization/massing model of the whole dock station. The
// printable part is sensor_node_enclosure.scad.
// ---------------------------------------------------------------------------

/* [Scene] */
show_crop   = true;
show_ground = true;

/* [Mast] */
mast_d      = 40;     // GI pipe
mast_h      = 1720;
mast_bury   = 450;

/* [Solar - 20 W, sized in docs/22_power_autonomy.md] */
panel_l     = 350;
panel_w     = 290;
panel_t     = 22;
panel_tilt  = 22;     // ~site latitude, central India
panel_z     = 1600;

/* [Main enclosure - compute + battery + comms] */
enc_l       = 220;
enc_w       = 160;
enc_h       = 95;
enc_z       = 1010;

/* [Camera head] */
cam_z       = 1310;
cam_tilt    = 35;     // degrees below horizontal
cam_arm     = 240;
cam_body    = [95, 75, 70];
hood_len    = 55;

/* [Crop] */
canopy_h    = 900;    // cotton at flowering

$fn = 48;

// ---------------------------------------------------------------------------
// Structure
// ---------------------------------------------------------------------------

module mast() {
    color("Gainsboro")
        translate([0, 0, -mast_bury]) cylinder(d = mast_d, h = mast_h + mast_bury);
    // ground anchor plate
    color("DimGray")
        translate([0, 0, -30]) cylinder(d = 190, h = 12, $fn = 6);
}

module solar_array() {
    translate([0, 0, panel_z]) {
        // tilt frame
        color("Silver")
            rotate([0, -panel_tilt, 0])
                translate([-panel_l / 2, -panel_w / 2, 0])
                    difference() {
                        cube([panel_l, panel_w, panel_t]);
                        translate([12, 12, -1])
                            cube([panel_l - 24, panel_w - 24, panel_t + 2]);
                    }
        // cells
        color("MidnightBlue")
            rotate([0, -panel_tilt, 0])
                translate([-panel_l / 2 + 8, -panel_w / 2 + 8, panel_t - 4])
                    cube([panel_l - 16, panel_w - 16, 5]);
        // wedge support onto the mast
        color("Silver")
            translate([-40, -30, -70]) cube([80, 60, 75]);
    }
}

module main_enclosure() {
    translate([-enc_l / 2, mast_d / 2 + 6, enc_z]) {
        color("SteelBlue") {
            // body
            hull() for (x = [12, enc_l - 12], y = [12, enc_w - 12])
                translate([x, y, 0]) cylinder(r = 12, h = enc_h);
            // rain-shedding lid overhang
            translate([-5, -5, enc_h])
                hull() for (x = [14, enc_l - 4], y = [14, enc_w - 4])
                    translate([x, y, 0]) cylinder(r = 14, h = 7);
        }
        // gland plate on the underside - cables always exit downward
        color("DimGray")
            for (i = [0 : 3])
                translate([45 + i * 35, enc_w / 2, -14]) cylinder(d = 14, h = 16);
        // status window
        color("Black")
            translate([enc_l / 2 - 30, -1, enc_h - 40]) cube([60, 4, 26]);
    }
    // mast straps
    color("DimGray")
        for (z = [enc_z + 18, enc_z + enc_h - 24])
            translate([0, 0, z]) difference() {
                cylinder(d = mast_d + 14, h = 12);
                translate([0, 0, -1]) cylinder(d = mast_d, h = 14);
            }
}

module antenna() {
    // Top of the mast: highest point, clear of the panel and the enclosure,
    // which is where a LoRa or LTE whip actually wants to be.
    color("Black") translate([0, 0, mast_h]) cylinder(d = 9, h = 210);
    color("DimGray") translate([0, 0, mast_h - 6]) cylinder(d = 22, h = 10);
}

module camera_head() {
    translate([0, 0, cam_z])
        rotate([0, 0, 0])
            translate([-mast_d / 2, 0, 0])
                rotate([0, cam_tilt, 0]) {
                    // arm
                    color("DimGray")
                        translate([-cam_arm, -14, -12]) cube([cam_arm, 28, 22]);
                    // sealed camera body
                    translate([-cam_arm - cam_body[0], -cam_body[1] / 2, -cam_body[2] + 10])
                        color("SteelBlue") cube(cam_body);
                    // sun hood - blocks direct sun off the lens without
                    // shadowing the canopy being photographed
                    color("DarkSlateGray")
                        translate([-cam_arm - cam_body[0] - hood_len,
                                   -cam_body[1] / 2 - 8, -cam_body[2] + 4])
                            difference() {
                                cube([hood_len, cam_body[1] + 16, cam_body[2] + 6]);
                                translate([-1, 8, 8])
                                    cube([hood_len + 2, cam_body[1], cam_body[2]]);
                            }
                    // lens
                    color("Black")
                        translate([-cam_arm - cam_body[0] - 2,
                                   0, -cam_body[2] / 2 + 10])
                            rotate([0, -90, 0]) cylinder(d = 30, h = 14);
                }
    // clamp
    color("DimGray")
        translate([0, 0, cam_z - 16]) difference() {
            cylinder(d = mast_d + 16, h = 34);
            translate([0, 0, -1]) cylinder(d = mast_d, h = 36);
        }
}

module soil_probes() {
    // shallow at 100 mm, root zone at 300 mm
    for (p = [[220, -110, 100], [300, -190, 300]]) {
        color("ForestGreen")
            translate([p[0], p[1], -p[2]]) cube([16, 4, p[2] + 30]);
        // cable back to the mast, sagging
        color("Black")
            for (t = [0 : 0.05 : 1])
                translate([p[0] * (1 - t), p[1] * (1 - t),
                           30 - 60 * sin(180 * t)])
                    sphere(d = 5);
    }
}

// ---------------------------------------------------------------------------
// Field context
// ---------------------------------------------------------------------------

module cotton_plant(h, seed) {
    color("SaddleBrown") cylinder(d = 14, h = h * 0.55);
    for (i = [0 : 6]) {
        a = (seed * 47 + i * 61) % 360;
        z = h * (0.30 + 0.10 * i);
        r = h * (0.20 - 0.015 * i);
        color("OliveDrab")
            translate([r * cos(a), r * sin(a), z])
                rotate([0, 28, a]) scale([1, 1, 0.20]) sphere(d = h * 0.15);
        color("Peru")
            translate([0, 0, z]) rotate([0, 62, a]) cylinder(d = 5, h = r);
    }
    for (i = [0 : 2]) {
        a = (seed * 91 + i * 120) % 360;
        color("WhiteSmoke")
            translate([h * 0.20 * cos(a), h * 0.20 * sin(a), h * 0.52])
                sphere(d = h * 0.045);
    }
}

module crop_rows() {
    for (row = [-1 : 1])
        for (col = [-2 : 2]) {
            x = col * 420 + row * 60;
            y = row * 430 - 520;
            if (!(abs(x) < 240 && abs(y) < 240))
                translate([x, y, 0])
                    cotton_plant(canopy_h * (0.85 + 0.3 * (((col + 3) * (row + 3)) % 5) / 5),
                                 col * 7 + row * 13);
        }
}

module ground() {
    color("Tan") translate([0, 0, -18]) cylinder(d = 2600, h = 18, $fn = 96);
}

// ---------------------------------------------------------------------------

mast();
solar_array();
main_enclosure();
antenna();
camera_head();
soil_probes();
if (show_crop) crop_rows();
if (show_ground) ground();
