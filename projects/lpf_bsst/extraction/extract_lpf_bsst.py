"""Extraction record for the LPF/BSST decarbonation specification.

This script is the *written record of the AI extraction* of
``source/Cahier des Charges P&ID Consolidé.pdf`` (3 pages).  It is project data, not part
of the generic pipeline: running it regenerates ``source_topology.json``, which is then
frozen.  Every object points back to a page and section of the PDF and says whether the
fact is stated explicitly, interpreted from the text, or structural (needed to express a
stated arrangement, e.g. a manifold for "3 pumps in parallel").

Run:  python projects/lpf_bsst/extraction/extract_lpf_bsst.py
"""

from __future__ import annotations

from pathlib import Path

from pid_workflow.schema import Topology
from pid_workflow.topology_io import save_topology

DOC = "Cahier des Charges P&ID Consolidé.pdf"
OUT = Path(__file__).resolve().parents[1] / "source_topology.json"

# ----------------------------------------------------------------------------- helpers


def S(page, section, quote=None, basis="explicit", note=None):
    return {
        "origin": "source",
        "document": DOC,
        "page": page,
        "section": section,
        "quote": quote,
        "basis": basis,
        "note": note,
    }


SEC_11 = "1.1 Zone de Captage et Boucle Fermenteurs"
SEC_12 = "1.2 Zone de Production de Chaleur (PAC) et Stockage"
SEC_13 = "1.3 Zone de Production de Vapeur (CMV)"
SEC_2 = "2. Lignes principales et réseaux de distribution"
SEC_3 = "3. Consommateurs process et modifications"
SEC_3_TEMP = "3. Maintien en température (Cuves LPF)"
SEC_3_DEG = "3. Dégazeur Thermique LPF"
SEC_3_AIR = "3. Préchauffage Air Process (BSST) – Exemple Tour TGE"
SEC_4 = "4. Logiques de régulation et modes opératoires"


def A(value, unit=None, prov=None):
    return {"value": value, "unit": unit, "provenance": prov}


topo: dict = {
    "schema_version": "1.0",
    "metadata": {
        "drawing_id": "PID-LPF-BSST-001",
        "title": "Décarbonation énergétique LPF & BSST – draft P&ID",
        "project": "Projet Décarbonation LPF & BSST",
        "revision": "A (draft for review)",
        "language": "en",
        "source_documents": [
            {
                "id": "cahier",
                "file": DOC,
                "pages": 3,
                "language": "fr",
                "title": "Cahier des Charges Topologique et Ingénierie P&ID",
            }
        ],
        "engineering_basis": [
            {
                "statement": "Standard CAD/ISA 5.1 look and tag nomenclature (e.g. PI-101, XV-201).",
                "provenance": S(3, "5. Règles topologiques génératives"),
            },
            {
                "statement": "Every pipe carries a Service attribute (e.g. Service=\"Steam 8 bar\").",
                "provenance": S(3, "5. Conventions graphiques et attributs DEXPI"),
            },
            {
                "statement": "Future equipment (PAC 3A/3B) carries LifeCyclePhase=\"Future\" (dashed rendering).",
                "provenance": S(3, "5. Conventions graphiques et attributs DEXPI"),
            },
        ],
    },
    "areas": [],
    "equipment": [],
    "components": [],
    "boundaries": [],
    "instruments": [],
    "process_lines": [],
    "signals": [],
    "control_requirements": [],
    "control_loops": [],
    "operating_modes": [],
    "unresolved_requirements": [],
    "modifications": [],
}

_ln = {"n": 0}


def area(id_, name, desc, prov):
    topo["areas"].append({"id": id_, "name": name, "description": desc, "provenance": prov})


def eq(
    id_,
    name,
    cls,
    area_,
    prov,
    tag=None,
    lifecycle="unspecified",
    nozzles=(),
    attrs=None,
):
    topo["equipment"].append(
        {
            "id": id_,
            "name": name,
            "tag": tag,
            "tag_status": "source" if tag else "none",
            "model_class": cls,
            "area": area_,
            "lifecycle": lifecycle,
            "nozzles": [
                {"name": n, "role": role, "number": None, "size": None, "service": None}
                for n, role in nozzles
            ],
            "attributes": attrs or {},
            "provenance": prov,
        }
    )


def manifold(id_, name, role, branches, area_, prov):
    topo["components"].append(
        {
            "id": id_,
            "name": name,
            "kind": "manifold",
            "model_class": "PipeTee",
            "role": role,
            "branches": branches,
            "area": area_,
            "provenance": prov,
        }
    )


def valve(id_, name, area_, prov, function, operation="unknown", attrs=None):
    topo["components"].append(
        {
            "id": id_,
            "name": name,
            "kind": "valve",
            "model_class": "CustomOperatedValve",
            "function": function,
            "technology": None,
            "technology_status": "unspecified_generic",
            "operation": operation,
            "tag": None,
            "tag_status": "none",
            "area": area_,
            "attributes": attrs or {},
            "provenance": prov,
        }
    )


def boundary(id_, name, direction, service, area_, prov, attrs=None):
    topo["boundaries"].append(
        {
            "id": id_,
            "name": name,
            "direction": direction,
            "service": service,
            "area": area_,
            "attributes": attrs or {},
            "provenance": prov,
        }
    )


def ref(s):
    obj, port = s.rsplit(":", 1)
    return {"ref": obj, "port": port}


def line(frm, to, service, prov, name=None, props=None, header=False, id_=None):
    if id_ is None:
        _ln["n"] += 1
        id_ = f"ln.{_ln['n']:03d}"
    topo["process_lines"].append(
        {
            "id": id_,
            "name": name,
            "service": service,
            "from": ref(frm),
            "to": ref(to),
            "logical_line": id_,
            "split_from": None,
            "line_number": None,
            "header": header,
            "properties": props or {},
            "provenance": prov,
        }
    )
    return id_


def fan_out(mf_id, mf_name, src, units, service, area_, prov, mprov, lprops=None):
    """src → split manifold → each unit port (parallel arrangement)."""
    manifold(mf_id, mf_name, "split", len(units), area_, mprov)
    if src:
        line(src, f"{mf_id}:common", service, prov, props=lprops)
    for i, u in enumerate(units, 1):
        line(f"{mf_id}:b{i}", u, service, prov, props=lprops)


def fan_in(mf_id, mf_name, units, dst, service, area_, prov, mprov, lprops=None):
    """each unit port → merge manifold → dst."""
    manifold(mf_id, mf_name, "merge", len(units), area_, mprov)
    for i, u in enumerate(units, 1):
        line(u, f"{mf_id}:b{i}", service, prov, props=lprops)
    if dst:
        line(f"{mf_id}:common", dst, service, prov, props=lprops)


def unresolved(id_, category, description, affects, prov, question=None, needed_for=None):
    topo["unresolved_requirements"].append(
        {
            "id": id_,
            "name": None,
            "category": category,
            "description": description,
            "affects": affects,
            "needed_for": needed_for,
            "question": question,
            "status": "open",
            "provenance": prov,
        }
    )


# --------------------------------------------------------------------------- areas

area("ar.well", "Well water & cooling loop", "Captage Puits 3, secours exchangers, fermenter loop (§1.1)", S(1, SEC_11))
area("ar.hp", "Heat pumps & hot-water storage", "PAC 1A/1B, 2A/2B, 3A/3B and buffer tanks (§1.2)", S(1, SEC_12))
area("ar.steam", "Steam production (CMV)", "Flash tank, 3-stage CMV, steam headers (§1.3)", S(1, SEC_13))
area("ar.lpf", "LPF consumers", "Tank heating, degasser, 4 bar users (§3)", S(2, SEC_3))
area("ar.bsst", "BSST consumers", "4 bar users and air-preheating coil (§3)", S(2, SEC_3))

# ----------------------------------------------------------------- §1.1 well + loop

P_WP = S(1, SEC_11, "3 pompes centrifuges à 50% de capacité (Tags: P-030, P-031, P-032), équipées de variateurs de fréquence, débit unitaire de 446,5 m3/h")
for i, (suf, tag) in enumerate([("a", "P-030"), ("b", "P-031"), ("c", "P-032")], 1):
    eq(
        f"eq.well_pump_{suf}", f"Well-water pump {i}/3", "CentrifugalPump", "ar.well", P_WP, tag=tag,
        lifecycle="new", nozzles=[("suction", "suction"), ("discharge", "discharge")],
        attrs={
            "capacity_fraction": A(50, "%", P_WP),
            "variable_frequency_drive": A(True, None, P_WP),
            "design_volume_flow_rate": A(446.5, "m3/h", P_WP),
        },
    )
P_ECH = S(1, SEC_11, "3 échangeurs à plaques à 50% (Tags: ECH-030, ECH-031, ECH-032), puissance unitaire de 8747 kW")
for i, (suf, tag) in enumerate([("a", "ECH-030"), ("b", "ECH-031"), ("c", "ECH-032")], 1):
    eq(
        f"eq.emerg_hx_{suf}", f"Emergency plate exchanger {i}/3", "PlateHeatExchanger", "ar.well", P_ECH, tag=tag,
        lifecycle="new",
        nozzles=[("cold_in", "inlet"), ("cold_out", "outlet"), ("hot_in", "inlet"), ("hot_out", "outlet")],
        attrs={
            "capacity_fraction": A(50, "%", P_ECH),
            "design_heat_flow_rate": A(8747, "kW", P_ECH),
        },
    )
P_LP = S(1, SEC_11, "3 pompes à 50% (Tags: P-033, P-034, P-035) avec variateurs, débit unitaire de 682,5 m3/h")
for i, (suf, tag) in enumerate([("a", "P-033"), ("b", "P-034"), ("c", "P-035")], 1):
    eq(
        f"eq.loop_pump_{suf}", f"PAC-loop pump {i}/3", "CentrifugalPump", "ar.well", P_LP, tag=tag,
        lifecycle="new", nozzles=[("suction", "suction"), ("discharge", "discharge")],
        attrs={
            "capacity_fraction": A(50, "%", P_LP),
            "variable_frequency_drive": A(True, None, P_LP),
            "design_volume_flow_rate": A(682.5, "m3/h", P_LP),
        },
    )
P_TK = S(1, SEC_12, "TK-001 (Eau froide 20°C), TK-002 (Eau chaude retour 31°C)")
eq("eq.tank_cold", "Buffer tank – cold water 20 °C", "Tank", "ar.well", P_TK, tag="TK-001", lifecycle="new",
   nozzles=[("inlet", "inlet"), ("outlet", "outlet")], attrs={"operating_temperature": A(20, "°C", P_TK)})
eq("eq.tank_warm", "Buffer tank – hot return water 31 °C", "Tank", "ar.well", P_TK, tag="TK-002", lifecycle="new",
   nozzles=[("inlet", "inlet"), ("outlet", "outlet")], attrs={"operating_temperature": A(31, "°C", P_TK)})
P_CF = S(2, SEC_3, "CF1 à 8, CFA, CFB", note="CF1-8 treated as one node; CFA/CFB listed as further fermenters in §3.")
eq("eq.fermenters", "Fermenters CF1-8, CFA, CFB", "CustomEquipment", "ar.well", P_CF, lifecycle="modified",
   nozzles=[("inlet", "inlet"), ("outlet", "outlet")],
   attrs={
       "members": A(["CF1", "CF2", "CF3", "CF4", "CF5", "CF6", "CF7", "CF8", "CFA", "CFB"], None, P_CF),
       "required_water_regime": A("20 °C in / 31 °C out", None, S(2, SEC_3, "Basculement sur nouveau régime d'eau 20°C / 31°C")),
   })
boundary("bc.well", "Puits 3 – well water source (12 °C)", "in", "Well water", "ar.well",
         S(1, SEC_11, "Puits 3 (température constante de 12°C)"), {"temperature": A(12, "°C")})
boundary("bc.darse", "Rejet vers DARSE (< 30 °C)", "out", "Well water", "ar.well",
         S(1, SEC_11, "Rejet vers DARSE (< 30°C)"), {"temperature_max": A(30, "°C")})

# ------------------------------------------------------------------- §1.2 heat pumps
HP_PROC = S(1, SEC_12, "PAC Process (1A / 1B) 2 (parallèle) 5,6 MW/u 8 MW/u 31°C / 20°C 70°C / 90°C R1234ze")
HP_RCUA = S(1, SEC_12, "PAC RCUA (2A / 2B) 2 (cascade) 3,8 MW/u 5,6 MW/u 31°C / 20°C 85°C / 105°C R1233zd/R1234ze")
HP_FUT = S(1, SEC_12, "PAC Extension (3A / 3B) 2 (cascade) – Équipement Futur (hors capacité)")
HP_NOZ = [("evap_in", "inlet"), ("evap_out", "outlet"), ("cond_in", "inlet"), ("cond_out", "outlet")]
JCI = S(1, SEC_12, "Quatre pompes à chaleur centrifuges de marque Johnson Controls")
for suf, lab in (("1a", "PAC 1A"), ("1b", "PAC 1B")):
    eq(f"eq.hp_{suf}", f"{lab} – process heat pump", "CustomEquipment", "ar.hp", HP_PROC, lifecycle="new",
       nozzles=HP_NOZ,
       attrs={
           "manufacturer": A("Johnson Controls", None, JCI), "compressor_type": A("centrifugal", None, JCI),
           "cold_power": A(5.6, "MW", HP_PROC), "hot_power": A(8, "MW", HP_PROC),
           "cold_regime": A("31 °C / 20 °C", None, HP_PROC), "hot_regime": A("70 °C / 90 °C", None, HP_PROC),
           "refrigerant": A("R1234ze", None, HP_PROC), "arrangement": A("parallel", None, HP_PROC),
       })
for suf, lab in (("2a", "PAC 2A"), ("2b", "PAC 2B")):
    eq(f"eq.hp_{suf}", f"{lab} – RCUA heat pump", "CustomEquipment", "ar.hp", HP_RCUA, lifecycle="new",
       nozzles=HP_NOZ,
       attrs={
           "manufacturer": A("Johnson Controls", None, JCI), "compressor_type": A("centrifugal", None, JCI),
           "cold_power": A(3.8, "MW", HP_RCUA), "hot_power": A(5.6, "MW", HP_RCUA),
           "cold_regime": A("31 °C / 20 °C", None, HP_RCUA), "hot_regime": A("85 °C / 105 °C", None, HP_RCUA),
           "refrigerant": A("R1233zd/R1234ze", None, HP_RCUA), "arrangement": A("cascade", None, HP_RCUA),
       })
for suf, lab in (("3a", "PAC 3A"), ("3b", "PAC 3B")):
    eq(f"eq.hp_{suf}", f"{lab} – extension heat pump (future)", "CustomEquipment", "ar.hp", HP_FUT, lifecycle="future",
       nozzles=HP_NOZ, attrs={"arrangement": A("cascade", None, HP_FUT)})

P_T70 = S(1, SEC_12, "Bâches Tampon (Nodes de stockage) : TK-001 (Eau froide 20°C), TK-002 (Eau chaude retour 31°C), Retour PAC (70°C), Départ PAC Process (90°C), et RCUA (85°C / 105°C)",
          note="Only TK-001/TK-002 carry tags; the other three buffer tanks are listed by service/temperature only.")
eq("eq.tank_70", "Buffer tank – PAC return 70 °C", "Tank", "ar.hp", P_T70, lifecycle="new",
   nozzles=[("inlet", "inlet"), ("outlet", "outlet")], attrs={"operating_temperature": A(70, "°C", P_T70)})
eq("eq.tank_90", "Buffer tank – PAC process supply 90 °C", "Tank", "ar.hp", P_T70, lifecycle="new",
   nozzles=[("inlet", "inlet"), ("outlet", "outlet")], attrs={"operating_temperature": A(90, "°C", P_T70)})
eq("eq.tank_rcua", "Buffer tank – RCUA 85/105 °C", "Tank", "ar.hp", dict(P_T70, basis="interpreted",
   note="'RCUA (85°C / 105°C)' read as ONE tank covering both temperatures of the RCUA loop (see ur.tank_count)."),
   lifecycle="new", nozzles=[("inlet", "inlet"), ("outlet", "outlet")],
   attrs={"operating_temperature": A("85 °C / 105 °C", None, P_T70)})

# -------------------------------------------------------------------------- §1.3 CMV
P_CMV = S(1, SEC_13, "1 ligne de Compression Mécanique de Vapeur sur 3 étages")
P_FLASH = S(1, SEC_13, "Alimentée par l'eau chaude à 90°C des PAC via un Flash Tank (70°C)")
eq("eq.flash_tank", "Flash tank (70 °C)", "Vessel", "ar.steam", P_FLASH, lifecycle="new",
   nozzles=[("hot_water_in", "inlet"), ("steam_out", "outlet"), ("liquid_out", "outlet")],
   attrs={"operating_temperature": A(70, "°C", P_FLASH)})
for n in (1, 2, 3):
    eq(f"eq.cmv_s{n}", f"CMV stage {n}", "CustomCompressor", "ar.steam", P_CMV, lifecycle="new",
       nozzles=[("inlet", "inlet"), ("outlet", "outlet")],
       attrs={
           "stage": A(n, None, P_CMV),
           "delivery_pressure": A({1: 1, 2: 4, 3: 8}[n], "bar eff.", S(1, SEC_13, "Distribution de vapeur nominale : 1 bar eff. (2,9 t/h) ; 4 bar eff. (9,1 t/h) ; 8 bar eff. (1,2 t/h)")),
       })
topo["equipment"][-1]["attributes"]["minimum_technical_production"] = A(
    5.8, "t/h", S(1, SEC_13, "La CMV impose une production minimale technique de 5,8 t/h à 8 bar eff."))
P_BOILER = S(3, SEC_4, "La chaudière gaz fournit 100% de la vapeur", note="Existing/new status of the boiler is not stated.")
eq("eq.boiler", "Gas boiler (standby)", "Boiler", "ar.steam", P_BOILER,
   nozzles=[("steam_out", "outlet")])

# ------------------------------------------------------------------ §3 LPF consumers
P_CUVE = S(2, SEC_3_TEMP, "Les cuves sont équipées de nouveaux échangeurs à plaques à eau chaude. Les anciens échangeurs vapeur sont conservés et montés en parallèle pour un usage de secours")
P_BAC = S(2, SEC_3, "BACS04, BACAN1, BACS05 Passage Vapeur vive -> Boucle Eau Chaude (90°C)")
for suf, tag in (("s04", "BACS04"), ("an1", "BACAN1"), ("s05", "BACS05")):
    eq(f"eq.lpf_tank_{suf}", f"LPF tank {tag}", "Tank", "ar.lpf", P_BAC, tag=tag, lifecycle="modified",
       nozzles=[("proc_out", "outlet"), ("proc_in", "inlet")],
       attrs={"heating_medium_change": A("live steam → hot-water loop (90 °C)", None, P_BAC)})
    eq(f"eq.lpf_phx_{suf}", f"New hot-water plate exchanger – {tag}", "PlateHeatExchanger", "ar.lpf",
       dict(P_CUVE, basis="interpreted", note=f"One new plate exchanger per listed LPF tank ({tag})."), lifecycle="new",
       nozzles=[("hot_in", "inlet"), ("hot_out", "outlet"), ("proc_in", "inlet"), ("proc_out", "outlet")])
    eq(f"eq.lpf_shx_{suf}", f"Retained steam exchanger (standby) – {tag}", "CustomHeatExchanger", "ar.lpf",
       dict(P_CUVE, basis="interpreted", note=f"Existing steam exchanger kept in parallel as backup for {tag}."), lifecycle="existing",
       nozzles=[("steam_in", "inlet"), ("condensate_out", "outlet"), ("proc_in", "inlet"), ("proc_out", "outlet")])
P_K3 = S(2, SEC_3, "K3, MESSO, GEA Abaissement alimentation vapeur à 4 bar eff.")
for suf, tag in (("k3", "K3"), ("messo", "MESSO"), ("gea", "GEA")):
    eq(f"eq.lpf_{suf}", f"LPF steam user {tag}", "CustomEquipment", "ar.lpf", P_K3, tag=tag, lifecycle="modified",
       nozzles=[("steam_in", "inlet")], attrs={"steam_supply_pressure": A(4, "bar eff.", P_K3)})
P_DEG = S(2, SEC_3_DEG, "Instancier un nouvel échangeur sur la ligne d'eau d'appoint (Eau Traitée) réchauffant le fluide de 12°C à 80°C avant la bâche de 44 m3")
eq("eq.lpf_degasser", "LPF thermal degasser with 44 m³ tank", "Vessel", "ar.lpf",
   S(2, SEC_3, "Dégazeur thermique LPF Alimentation en 4 bar ou 1 bar eff. (à définir)", note="Degasser and its 44 m³ bâche modelled as one vessel."),
   lifecycle="modified", nozzles=[("water_in", "inlet"), ("steam_in", "inlet")],
   attrs={"tank_volume": A(44, "m3", P_DEG)})
eq("eq.lpf_degasser_hx", "New make-up water heater (12 → 80 °C)", "PlateHeatExchanger", "ar.lpf", P_DEG, lifecycle="new",
   nozzles=[("cold_in", "inlet"), ("cold_out", "outlet"), ("hot_in", "inlet"), ("hot_out", "outlet")],
   attrs={"cold_inlet_temperature": A(12, "°C", P_DEG), "cold_outlet_temperature": A(80, "°C", P_DEG)})
boundary("bc.makeup", "Treated make-up water (Eau Traitée, 12 °C)", "in", "Treated make-up water", "ar.lpf", P_DEG,
         {"temperature": A(12, "°C", P_DEG)})

# ----------------------------------------------------------------- §3 BSST consumers
P_BS = S(2, SEC_3, "TGEA, TGEB, Finisseur Abaissement alimentation vapeur à 4 bar eff.; Tour ICF (Évaporateur) Abaissement alimentation vapeur à 4 bar eff.")
for suf, tag, nm in (("tgea", "TGEA", "BSST steam user TGEA"), ("tgeb", "TGEB", "BSST steam user TGEB"),
                     ("finisher", "Finisseur", "BSST steam user Finisseur"), ("icf", "Tour ICF", "BSST steam user Tour ICF (evaporator)")):
    eq(f"eq.bsst_{suf}", nm, "CustomEquipment", "ar.bsst", P_BS, tag=None, lifecycle="modified",
       nozzles=[("steam_in", "inlet")],
       attrs={"label": A(tag, None, P_BS), "steam_supply_pressure": A(4, "bar eff.", P_BS)})
P_AIR = S(2, SEC_3_AIR, "Instancier de nouvelles batteries à eau chaude en amont des ventilateurs. Paramètres d'ingénierie : Entrée eau limitée à 85°C (sécurité sanitaire). Sortie eau 65°C. Débit d'eau: 20 769 l/h. Air process (40 000 m3/h) chauffé de -15°C à 20°C. Raccordements DN50.")
eq("eq.bsst_tge_coil", "Air-preheating hot-water coil (TGE example)", "CustomHeatExchanger", "ar.bsst", P_AIR, lifecycle="new",
   nozzles=[("hot_in", "inlet"), ("hot_out", "outlet")],
   attrs={
       "water_inlet_temperature_max": A(85, "°C", P_AIR), "water_outlet_temperature": A(65, "°C", P_AIR),
       "water_flow_rate": A(20769, "l/h", P_AIR), "air_flow_rate": A(40000, "m3/h", P_AIR),
       "air_inlet_temperature": A(-15, "°C", P_AIR), "air_outlet_temperature": A(20, "°C", P_AIR),
   })
for z in topo["equipment"][-1]["nozzles"]:
    z["size"] = A("DN50", None, P_AIR)

# ===================================================================== connections
L11 = S(1, SEC_11)
STR = lambda page, sec, quote: S(page, sec, quote, basis="structural")  # noqa: E731

# ---- well water: source → pumps → emergency exchangers (cold side) → DARSE
fan_out("mf.wp_s", "Well-pump suction manifold", "bc.well:port",
        [f"eq.well_pump_{s}:suction" for s in "abc"], "Well water", "ar.well",
        S(1, SEC_11, "Pompage Primaire (Puits 3)"), STR(1, SEC_11, "3 pompes centrifuges à 50% de capacité"))
fan_in("mf.wp_d", "Well-pump discharge manifold", [f"eq.well_pump_{s}:discharge" for s in "abc"], None,
       "Well water", "ar.well", S(1, SEC_11, "Pompage Primaire (Puits 3)"), STR(1, SEC_11, "3 pompes centrifuges à 50% de capacité"))
fan_out("mf.ech_cw_s", "Emergency-exchanger well-water inlet manifold", "mf.wp_d:common",
        [f"eq.emerg_hx_{s}:cold_in" for s in "abc"], "Well water", "ar.well",
        S(1, SEC_11, "Échangeurs de Secours : 3 échangeurs à plaques à 50%", basis="interpreted",
          note="Well water is the cooling medium of the emergency exchangers (§4: 'les échangeurs de secours refroidissent l'eau des fermenteurs')."),
        STR(1, SEC_11, "3 échangeurs à plaques à 50%"))
fan_in("mf.ech_cw_m", "Emergency-exchanger well-water outlet manifold", [f"eq.emerg_hx_{s}:cold_out" for s in "abc"], None,
       "Well water", "ar.well", S(1, SEC_11, "Rejet vers DARSE (< 30°C)"), STR(1, SEC_11, "3 échangeurs à plaques à 50%"))
manifold("mf.darse_m", "DARSE discharge manifold", "merge", 2, "ar.well",
         STR(3, SEC_4, "L'eau de forage post-fermenteurs est déchargée directement vers la DARSE"))
line("mf.ech_cw_m:common", "mf.darse_m:b1", "Well water", S(1, SEC_11, "Rejet vers DARSE (< 30°C)"))
line("mf.darse_m:common", "bc.darse:port", "Well water", S(1, SEC_11, "Rejet vers DARSE (< 30°C)"),
     props={"temperature_max": A(30, "°C", S(1, SEC_11, "Rejet vers DARSE (< 30°C)"))})

# ---- cooling-water loop (20 °C supply / 31 °C return)
P_CW = S(2, SEC_2, "Eau de refroidissement DN 600 (minimum) Aller 20°C / Retour 31°C PAC (Évaporateurs) <-> Fermenteurs CF1-8")
CWSUP = {"nominal_diameter_min": A(600, "DN", P_CW), "temperature": A(20, "°C", P_CW)}
CWRET = {"nominal_diameter_min": A(600, "DN", P_CW), "temperature": A(31, "°C", P_CW)}
line("eq.tank_cold:outlet", "eq.fermenters:inlet", "Cooling water 20/31", P_CW, name="Cooling-water supply to fermenters (20 °C)", props=CWSUP)
line("eq.fermenters:outlet", "mf.ferm_out:common", "Cooling water 20/31", P_CW, name="Cooling-water return from fermenters (31 °C)", props=CWRET)
manifold("mf.ferm_out", "Fermenter outlet manifold", "split", 2, "ar.well",
         STR(3, SEC_4, "L'eau de forage post-fermenteurs est déchargée directement vers la DARSE"))
line("mf.ferm_out:b1", "eq.tank_warm:inlet", "Cooling water 20/31", P_CW, props=CWRET)
line("mf.ferm_out:b2", "mf.darse_m:b2", "Well water", S(3, SEC_4, "L'eau de forage post-fermenteurs est déchargée directement vers la DARSE"),
     name="Ultimate-backup discharge to DARSE")
fan_out("mf.lp_s", "PAC-loop pump suction manifold", "eq.tank_warm:outlet",
        [f"eq.loop_pump_{s}:suction" for s in "abc"], "Cooling water 20/31", "ar.well",
        dict(P_CW, basis="interpreted", note="Pumps P-033..035 are the 'Pompage Secondaire (Boucle PAC)'; their position on the loop is not stated (see ur.loop_pump_position)."),
        STR(1, SEC_11, "3 pompes à 50% (Tags: P-033, P-034, P-035)"), lprops={"temperature": A(31, "°C", P_CW)})
fan_in("mf.lp_d", "PAC-loop pump discharge manifold", [f"eq.loop_pump_{s}:discharge" for s in "abc"], None,
       "Cooling water 20/31", "ar.well", dict(P_CW, basis="interpreted"), STR(1, SEC_11, "3 pompes à 50% (Tags: P-033, P-034, P-035)"),
       lprops={"temperature": A(31, "°C", P_CW)})
evap_units = ["eq.hp_1a", "eq.hp_1b", "eq.hp_2a"]
fan_out("mf.cw_s", "Cold-water distribution manifold (evaporators + emergency exchangers)", "mf.lp_d:common",
        [f"{u}:evap_in" for u in evap_units] + [f"eq.emerg_hx_{s}:hot_in" for s in "abc"],
        "Cooling water 20/31", "ar.well",
        dict(P_CW, basis="interpreted",
             note="Emergency exchangers placed in PARALLEL with the evaporators (see ur.ech_position)."),
        STR(1, SEC_12, "PAC Process (1A / 1B) 2 (parallèle)"), lprops={"temperature": A(31, "°C", P_CW)})
fan_in("mf.cw_m", "Cold-water collection manifold", [f"{u}:evap_out" for u in evap_units] + [f"eq.emerg_hx_{s}:hot_out" for s in "abc"],
       "eq.tank_cold:inlet", "Cooling water 20/31", "ar.well", dict(P_CW, basis="interpreted"),
       STR(1, SEC_12, "PAC Process (1A / 1B) 2 (parallèle)"), lprops={"temperature": A(20, "°C", P_CW)})

# ---- hot water process 70/90 loop through PAC 1A/1B condensers
P_HW = S(2, SEC_2, "Eau Chaude Process DN 200 à DN 350 Aller 90°C / Retour 70°C PAC (Condenseurs) -> Cuves / Échangeurs air")
HWP = {"nominal_diameter_range": A({"min": 200, "max": 350}, "DN", P_HW)}
HWSUP = dict(HWP, temperature=A(90, "°C", P_HW))
HWRET = dict(HWP, temperature=A(70, "°C", P_HW))
fan_out("mf.hp1_c_s", "PAC 1A/1B condenser inlet manifold", "eq.tank_70:outlet", ["eq.hp_1a:cond_in", "eq.hp_1b:cond_in"],
        "Hot water 90/70", "ar.hp", dict(P_HW, basis="interpreted", note="PAC process condensers fed from the 70 °C return tank."),
        STR(1, SEC_12, "PAC Process (1A / 1B) 2 (parallèle)"), lprops=HWRET)
fan_in("mf.hp1_c_m", "PAC 1A/1B condenser outlet manifold", ["eq.hp_1a:cond_out", "eq.hp_1b:cond_out"], "eq.tank_90:inlet",
       "Hot water 90/70", "ar.hp", dict(P_HW, basis="interpreted", note="Condenser outlets (90 °C) collected in the 90 °C departure tank."),
       STR(1, SEC_12, "PAC Process (1A / 1B) 2 (parallèle)"), lprops=HWSUP)
cons_in = ["eq.lpf_phx_s04:hot_in", "eq.lpf_phx_an1:hot_in", "eq.lpf_phx_s05:hot_in", "eq.bsst_tge_coil:hot_in", "eq.flash_tank:hot_water_in"]
manifold("mf.hw90_s", "Hot-water 90 °C distribution manifold", "split", len(cons_in), "ar.hp",
         STR(2, SEC_2, "Eau Chaude Process ... PAC (Condenseurs) -> Cuves / Échangeurs air"))
line("eq.tank_90:outlet", "mf.hw90_s:common", "Hot water 90/70", P_HW, id_="ln.hw90", name="Hot-water 90 °C header", props=HWSUP, header=True)
for i, c in enumerate(cons_in, 1):
    pr = S(2, SEC_2, "Eau Chaude Process ... -> Cuves / Échangeurs air") if "flash" not in c else S(1, SEC_13, "Alimentée par l'eau chaude à 90°C des PAC via un Flash Tank (70°C)")
    line(f"mf.hw90_s:b{i}", c, "Hot water 90/70", dict(pr, basis="interpreted") if "flash" in c else pr, props=HWSUP)
ret_out = ["eq.lpf_phx_s04:hot_out", "eq.lpf_phx_an1:hot_out", "eq.lpf_phx_s05:hot_out", "eq.bsst_tge_coil:hot_out"]
fan_in("mf.hw70_m", "Hot-water return manifold", ret_out, "eq.tank_70:inlet", "Hot water 90/70", "ar.hp",
       dict(P_HW, basis="interpreted", note="Return side of the 90/70 °C regime, collected in the 70 °C tank."),
       STR(2, SEC_2, "Aller 90°C / Retour 70°C"), lprops=HWRET)

# ---- RCUA cascade 2A/2B
P_RC = S(2, SEC_2, "Boucle Interne PAC 2A/2B (RCUA) À définir 55°C / 50°C Condenseur PAC 2A (sortie) -> Évaporateur PAC 2B (entrée)")
line("eq.hp_2a:cond_out", "eq.hp_2b:evap_in", "Internal loop PAC 2A/2B 55/50", P_RC, id_="ln.pac2_internal",
     name="PAC 2A condenser → PAC 2B evaporator (internal loop)",
     props={"nominal_diameter": A(None, "DN", S(2, SEC_2, "À définir")), "temperature_supply": A(55, "°C", P_RC), "temperature_return": A(50, "°C", P_RC)})
line("eq.hp_2b:evap_out", "eq.hp_2a:cond_in", "Internal loop PAC 2A/2B 55/50",
     S(2, SEC_2, "55°C / 50°C", basis="interpreted", note="Return leg of the internal loop is implied by the 55/50 °C regime, not drawn in the text."),
     name="PAC 2B evaporator → PAC 2A condenser (internal loop return)",
     props={"temperature_return": A(50, "°C", P_RC)})
P_RCH = S(1, SEC_12, "PAC RCUA (2A / 2B) ... 85°C / 105°C")
line("eq.tank_rcua:outlet", "eq.hp_2b:cond_in", "Hot water RCUA 85/105", dict(P_RCH, basis="interpreted"), name="RCUA return (85 °C) to PAC 2B condenser",
     props={"temperature": A(85, "°C", P_RCH)})
line("eq.hp_2b:cond_out", "bc.rcua_out:port", "Hot water RCUA 85/105", dict(P_RCH, basis="interpreted"), id_="ln.h105",
     name="Hot-water 105 °C header (RCUA)", props={"temperature": A(105, "°C", P_RCH)}, header=True)
boundary("bc.rcua_out", "RCUA network – supply 105 °C (placeholder battery limit)", "out", "Hot water RCUA 85/105", "ar.hp",
         S(3, "5. Instrumentation des Collecteurs (Headers)", "collecteurs principaux de vapeur (1, 4, 8 bar) et d'eau chaude (90°C, 105°C)", basis="interpreted",
           note="The PDF names a 105 °C hot-water header but not its destination; placeholder boundary."))
boundary("bc.rcua_return", "RCUA network – return 85 °C (placeholder battery limit)", "in", "Hot water RCUA 85/105", "ar.hp",
         S(1, SEC_12, "RCUA (85°C / 105°C)", basis="interpreted", note="Placeholder battery limit; the RCUA network itself is not described."))
line("bc.rcua_return:port", "eq.tank_rcua:inlet", "Hot water RCUA 85/105", dict(P_RCH, basis="interpreted"), name="RCUA return",
     props={"temperature": A(85, "°C", P_RCH)})

# ---- CMV and steam headers
P_ST = S(2, SEC_2, "Vapeur Haute Pression DN 150 8 bar eff. CMV (Étage 3) -> Réseau BSST; Vapeur Moyenne Pression DN 300 4 bar eff. CMV (Étage 2) -> Réseaux LPF et BSST Sud; Vapeur Basse Pression DN 200 1 bar eff. CMV (Étage 1) -> Réseau BSST Nord")
P_FS = S(1, SEC_13, "Alimentée par l'eau chaude à 90°C des PAC via un Flash Tank (70°C)", basis="interpreted",
         note="Vapour from the flash tank is the suction of CMV stage 1.")
P_IS = S(1, SEC_13, "1 ligne de Compression Mécanique de Vapeur sur 3 étages", basis="interpreted",
         note="Three stages of one line are read as a series compression train (stage n outlet feeds stage n+1 inlet).")
line("eq.flash_tank:steam_out", "eq.cmv_s1:inlet", "Flash steam", P_FS, name="Flash-tank vapour to CMV stage 1")
manifold("mf.s1_tap", "CMV stage 1 outlet manifold", "split", 2, "ar.steam", STR(2, SEC_2, "CMV (Étage 1) -> Réseau BSST Nord"))
manifold("mf.s2_tap", "CMV stage 2 outlet manifold", "split", 2, "ar.steam", STR(2, SEC_2, "CMV (Étage 2) -> Réseaux LPF et BSST Sud"))
manifold("mf.mh1", "1 bar header junction", "merge", 2, "ar.steam", STR(3, SEC_4, "route l'excédent de 8 bar vers le 4 bar, puis vers le 1 bar"))
manifold("mf.mh4", "4 bar header junction", "merge", 2, "ar.steam", STR(3, SEC_4, "route l'excédent de 8 bar vers le 4 bar, puis vers le 1 bar"))
manifold("mf.mh8", "8 bar header junction", "merge", 2, "ar.steam", STR(3, SEC_4, "La chaudière s'active via une vanne de régulation automatique (PCV)"))
manifold("mf.sp8", "8 bar header split", "split", 2, "ar.steam", STR(3, SEC_4, "route l'excédent de 8 bar vers le 4 bar"))
manifold("mf.sp4", "4 bar header split", "split", 3, "ar.steam", STR(2, SEC_2, "CMV (Étage 2) -> Réseaux LPF et BSST Sud"))
S1P = {"nominal_diameter": A(200, "DN", P_ST), "pressure": A(1, "bar eff.", P_ST), "nominal_flow": A(2.9, "t/h", P_ST)}
S4P = {"nominal_diameter": A(300, "DN", P_ST), "pressure": A(4, "bar eff.", P_ST), "nominal_flow": A(9.1, "t/h", P_ST)}
S8P = {"nominal_diameter": A(150, "DN", P_ST), "pressure": A(8, "bar eff.", P_ST), "nominal_flow": A(1.2, "t/h", P_ST)}
line("eq.cmv_s1:outlet", "mf.s1_tap:common", "Steam 1 bar", P_IS, name="CMV stage 1 outlet")
line("mf.s1_tap:b1", "eq.cmv_s2:inlet", "Steam 1 bar", P_IS, name="Inter-stage 1→2")
line("mf.s1_tap:b2", "mf.mh1:b1", "Steam 1 bar", P_ST, props=S1P)
line("mf.mh1:common", "bc.vap1:port", "Steam 1 bar", P_ST, id_="ln.h1", name="Steam 1 bar header", props=S1P, header=True)
boundary("bc.vap1", "Réseau BSST Nord (1 bar eff.)", "out", "Steam 1 bar", "ar.steam", S(2, SEC_2, "CMV (Étage 1) -> Réseau BSST Nord"))
line("eq.cmv_s2:outlet", "mf.s2_tap:common", "Steam 4 bar", P_IS, name="CMV stage 2 outlet")
line("mf.s2_tap:b1", "eq.cmv_s3:inlet", "Steam 4 bar", P_IS, name="Inter-stage 2→3")
line("mf.s2_tap:b2", "mf.mh4:b1", "Steam 4 bar", P_ST, props=S4P)
line("mf.mh4:common", "mf.sp4:common", "Steam 4 bar", P_ST, id_="ln.h4", name="Steam 4 bar header", props=S4P, header=True)
line("eq.cmv_s3:outlet", "mf.mh8:b1", "Steam 8 bar", P_ST, name="CMV stage 3 outlet", props=S8P)
line("mf.mh8:common", "mf.sp8:common", "Steam 8 bar", P_ST, id_="ln.h8", name="Steam 8 bar header", props=S8P, header=True)
line("mf.sp8:b1", "bc.vap8:port", "Steam 8 bar", P_ST, props=S8P)
boundary("bc.vap8", "Réseau BSST (8 bar eff.)", "out", "Steam 8 bar", "ar.steam", S(2, SEC_2, "CMV (Étage 3) -> Réseau BSST"))

# control valves (source: PCVs named in §4)
P_PCVB = S(3, SEC_4, "La chaudière s'active via une vanne de régulation automatique (PCV) si la pression du collecteur 8 bar chute sous le seuil exact de 7,5 bar eff.")
P_PCVS = S(3, SEC_4, "une vanne déversante (PCV) route l'excédent de 8 bar vers le 4 bar, puis vers le 1 bar")
valve("pc.pcv_boiler", "Boiler back-up pressure control valve (PCV)", "ar.steam", P_PCVB, "control", "automated")
valve("pc.pcv_spill_8_4", "Overproduction spill valve 8 → 4 bar (PCV)", "ar.steam", P_PCVS, "control", "automated")
valve("pc.pcv_spill_4_1", "Overproduction spill valve 4 → 1 bar (PCV)", "ar.steam", P_PCVS, "control", "automated")
line("eq.boiler:steam_out", "pc.pcv_boiler:in", "Steam 8 bar", P_PCVB, name="Boiler steam to PCV")
line("pc.pcv_boiler:out", "mf.mh8:b2", "Steam 8 bar", P_PCVB, name="Boiler back-up steam to 8 bar header")
line("mf.sp8:b2", "pc.pcv_spill_8_4:in", "Steam 8 bar", P_PCVS, name="8 bar excess to spill valve")
line("pc.pcv_spill_8_4:out", "mf.mh4:b2", "Steam 4 bar", P_PCVS, name="Spilled steam into 4 bar header")
line("mf.sp4:b3", "pc.pcv_spill_4_1:in", "Steam 4 bar", P_PCVS, name="4 bar excess to spill valve")
line("pc.pcv_spill_4_1:out", "mf.mh1:b2", "Steam 1 bar", P_PCVS, name="Spilled steam into 1 bar header")

# steam networks to consumers (4 bar)
P_N4 = S(2, SEC_2, "Vapeur Moyenne Pression ... CMV (Étage 2) -> Réseaux LPF et BSST Sud")
lpf_users = ["eq.lpf_k3:steam_in", "eq.lpf_messo:steam_in", "eq.lpf_gea:steam_in"]
bs_users = [f"eq.bsst_{s}:steam_in" for s in ("tgea", "tgeb", "finisher", "icf")]
manifold("mf.net_lpf4", "LPF 4 bar steam network", "split", len(lpf_users), "ar.lpf", STR(2, SEC_3, "K3, MESSO, GEA Abaissement alimentation vapeur à 4 bar eff."))
manifold("mf.net_bsst4", "BSST Sud 4 bar steam network", "split", len(bs_users), "ar.bsst", STR(2, SEC_3, "TGEA, TGEB, Finisseur ... Abaissement alimentation vapeur à 4 bar eff."))
line("mf.sp4:b1", "mf.net_lpf4:common", "Steam 4 bar", P_N4, name="4 bar steam to Réseau LPF", props=S4P)
line("mf.sp4:b2", "mf.net_bsst4:common", "Steam 4 bar", P_N4, name="4 bar steam to Réseau BSST Sud", props=S4P)
for i, u in enumerate(lpf_users, 1):
    line(f"mf.net_lpf4:b{i}", u, "Steam 4 bar", dict(P_K3, basis="interpreted", note="Users listed under LPF are supplied from the LPF 4 bar network."))
for i, u in enumerate(bs_users, 1):
    line(f"mf.net_bsst4:b{i}", u, "Steam 4 bar", dict(P_BS, basis="interpreted", note="Users listed under BSST are supplied from the BSST Sud 4 bar network."))

# ---- LPF tank maintenance loops (new plate exchanger in parallel with the retained steam exchanger)
for suf in ("s04", "an1", "s05"):
    manifold(f"mf.lpf_loop_s_{suf}", f"Tank {suf.upper()} heating-loop split", "split", 2, "ar.lpf", STR(2, SEC_3_TEMP, "montés en parallèle"))
    manifold(f"mf.lpf_loop_m_{suf}", f"Tank {suf.upper()} heating-loop merge", "merge", 2, "ar.lpf", STR(2, SEC_3_TEMP, "montés en parallèle"))
    pr = dict(P_CUVE, basis="interpreted", note="Process side of the new and the retained exchanger in parallel; the circulation arrangement is not described.")
    line(f"eq.lpf_tank_{suf}:proc_out", f"mf.lpf_loop_s_{suf}:common", "Process fluid (LPF tank)", pr)
    line(f"mf.lpf_loop_s_{suf}:b1", f"eq.lpf_phx_{suf}:proc_in", "Process fluid (LPF tank)", pr)
    line(f"mf.lpf_loop_s_{suf}:b2", f"eq.lpf_shx_{suf}:proc_in", "Process fluid (LPF tank)", pr)
    line(f"eq.lpf_phx_{suf}:proc_out", f"mf.lpf_loop_m_{suf}:b1", "Process fluid (LPF tank)", pr)
    line(f"eq.lpf_shx_{suf}:proc_out", f"mf.lpf_loop_m_{suf}:b2", "Process fluid (LPF tank)", pr)
    line(f"mf.lpf_loop_m_{suf}:common", f"eq.lpf_tank_{suf}:proc_in", "Process fluid (LPF tank)", pr)

# ---- LPF degasser make-up line
line("bc.makeup:port", "eq.lpf_degasser_hx:cold_in", "Treated make-up water", P_DEG, name="Make-up water to new heater",
     props={"temperature": A(12, "°C", P_DEG)})
line("eq.lpf_degasser_hx:cold_out", "eq.lpf_degasser:water_in", "Treated make-up water", P_DEG,
     name="Heated make-up water to degasser tank (44 m³)", props={"temperature": A(80, "°C", P_DEG)})

# ================================================================== §4 control & modes
topo["control_requirements"].append({
    "id": "cr.boiler_backup", "name": "Boiler back-up on low 8 bar pressure",
    "description": "The gas boiler is activated through an automatic control valve (PCV) when the 8 bar header pressure falls below 7.5 bar eff.",
    "controlled_variable": "pressure", "measured_at_line": "ln.h8", "final_element": "pc.pcv_boiler",
    "setpoint": A(7.5, "bar eff.", S(3, SEC_4, "sous le seuil exact de 7,5 bar eff.")),
    "controller_required": True, "action": "open the PCV when the measured pressure is below the setpoint",
    "provenance": P_PCVB, "attributes": {},
})
for cid, valve_id, nm in (("cr.spill_8_4", "pc.pcv_spill_8_4", "8 → 4 bar"), ("cr.spill_4_1", "pc.pcv_spill_4_1", "4 → 1 bar")):
    topo["control_requirements"].append({
        "id": cid, "name": f"Overproduction spill {nm}",
        "description": f"A spill PCV routes the 8 bar surplus ({nm} stage of the cascade). Controlled variable, measurement point and setpoint are NOT stated.",
        "controlled_variable": None, "measured_at_line": None, "final_element": valve_id, "setpoint": None,
        "controller_required": True, "action": None, "provenance": P_PCVS, "attributes": {},
    })

cool_targets = [ref(f"{u}:evap_in") for u in evap_units] + [ref(f"eq.emerg_hx_{s}:hot_in") for s in "abc"]
pac_targets = [ref(f"{u}:evap_in") for u in evap_units]
topo["operating_modes"] = [
    {"id": "mode.normal", "name": "Normal mode", "attributes": {},
     "description": "Cooling water passes the (inactive) emergency exchangers and then the PAC 1A/1B and 2A/2B; the CMV produces steam.",
     "requirements": [{"action": "operate", "targets": [], "text": "Emergency exchangers inactive; PAC 1A/1B/2A/2B and CMV in operation."}],
     "provenance": S(3, SEC_4, "Mode Normal : L'eau de forage passe par les échangeurs de secours (inactifs) puis vers les PAC 1A/1B et 2A/2B. La CMV produit la vapeur.")},
    {"id": "mode.emergency_hx", "name": "Emergency-exchanger mode (PAC stopped)", "attributes": {},
     "description": "PAC are isolated; emergency exchangers cool the fermenter water; the gas boiler supplies 100 % of the steam; hot-water networks fall back to local steam.",
     "requirements": [
         {"action": "isolate", "targets": pac_targets, "text": "PAC isolated."},
         {"action": "operate", "targets": [ref(f"eq.emerg_hx_{s}:hot_in") for s in "abc"], "text": "Emergency exchangers cool the fermenter water."},
         {"action": "operate", "targets": [ref("eq.boiler:steam_out")], "text": "Gas boiler supplies 100 % of the steam."},
         {"action": "note", "targets": [], "text": "Hot-water networks switch to local steam back-up (equipment not described)."}],
     "provenance": S(3, SEC_4, "Mode Secours Échangeurs (PAC à l'arrêt) : Les PAC sont isolées. Les échangeurs de secours refroidissent l'eau des fermenteurs.")},
    {"id": "mode.ultimate", "name": "Ultimate emergency mode (total shutdown)", "attributes": {},
     "description": "Isolation valves toward PAC and exchangers closed; post-fermenter well water is discharged directly to DARSE.",
     "requirements": [
         {"action": "isolate", "targets": cool_targets, "text": "Isolation valves toward PAC and emergency exchangers closed."},
         {"action": "discharge", "targets": [ref("mf.ferm_out:b2")], "text": "Post-fermenter well water discharged directly to DARSE."}],
     "provenance": S(3, SEC_4, "Mode Secours Ultime (Arrêt Total) : Vannes d'isolement fermées vers PAC et échangeurs. L'eau de forage post-fermenteurs est déchargée directement vers la DARSE.")},
    {"id": "mode.boiler_standby", "name": "Gas boiler standby", "attributes": {},
     "description": "Boiler starts through the PCV when the 8 bar header drops below 7.5 bar eff.",
     "requirements": [{"action": "operate", "targets": [ref("pc.pcv_boiler:in")], "text": "PCV opens below 7.5 bar eff. on the 8 bar header."}],
     "provenance": P_PCVB},
    {"id": "mode.overproduction", "name": "8 bar overproduction management", "attributes": {},
     "description": "CMV minimum 5.8 t/h at 8 bar; the surplus is spilled by cascade 8 → 4 → 1 bar through PCVs.",
     "requirements": [{"action": "operate", "targets": [ref("pc.pcv_spill_8_4:in"), ref("pc.pcv_spill_4_1:in")], "text": "Spill cascade 8 → 4 → 1 bar."}],
     "provenance": P_PCVS},
]

# ============================================================== unresolved requirements
U = unresolved
U("ur.ech_position", "ambiguity",
  "Position of the emergency exchangers (ECH-030..032) on the cooling loop is ambiguous. §4 'Mode Normal' reads like a series path (through the exchangers, then to the PAC); §4 'Secours Échangeurs' (PAC isolated, exchangers cooling) and 'Secours Ultime' (valves closed toward PAC *and* exchangers) need them as a separate parallel branch. Modelled in PARALLEL with the evaporators.",
  ["eq.emerg_hx_a", "eq.emerg_hx_b", "eq.emerg_hx_c", "mf.cw_s", "mf.cw_m"], S(3, SEC_4), question="Confirm parallel arrangement and the well-water path in Normal mode.", needed_for="cooling-loop topology")
U("ur.loop_pump_position", "ambiguity",
  "Pumps P-033..035 are called 'Pompage Secondaire (Boucle PAC)'; no circulation driver is stated for the TK-001 → fermenters leg or for the hot-water loops (PAC condensers, 90 °C and RCUA distribution). Pumps were not invented; P-033..035 sit on the TK-002 outlet feeding the PAC/exchanger branches.",
  ["eq.loop_pump_a", "eq.loop_pump_b", "eq.loop_pump_c", "eq.tank_cold", "eq.tank_70", "eq.tank_90", "eq.tank_rcua"], S(1, SEC_11),
  question="Where are the circulation pumps of the fermenter leg and of the hot-water loops?", needed_for="pump auxiliaries, loop hydraulics")
U("ur.cascade_2a_2b", "conflict",
  "PAC 2A/2B: the table gives both units a 31/20 °C cold regime and 85/105 °C hot regime, but §2 routes the 2A condenser outlet (55 °C) into the 2B evaporator inlet. Modelled as a physical cascade: 2A evaporator on the cooling loop; 2A condenser ⇄ 2B evaporator via the 55/50 °C internal loop; only 2B condenser on the 85/105 °C RCUA loop. The 2B evaporator therefore has no cooling-loop connection, contrary to its table row.",
  ["eq.hp_2a", "eq.hp_2b", "ln.pac2_internal"], S(2, SEC_2), question="Confirm the 2A/2B cascade connections.", needed_for="PAC 2A/2B nozzle connections")
U("ur.internal_loop", "missing_value", "Internal loop PAC 2A/2B: nominal diameter is 'À définir'; the 50 °C return leg is implied, not stated.",
  ["ln.pac2_internal"], S(2, SEC_2, "À définir"), question="DN of the internal loop and confirmation of its return leg.")
U("ur.future_hp", "scope", "PAC 3A/3B are future equipment with no capacity, regime or connection data. They are drawn dashed (LifeCyclePhase=Future) and left unconnected.",
  ["eq.hp_3a", "eq.hp_3b"], HP_FUT)
U("ur.hw_dn", "missing_value", "Hot-water process lines: only a range 'DN 200 à DN 350' is given; per-line diameters are not defined. Branch lines of the cooling-water loop carry only the 'DN 600 minimum' of the main lines.",
  ["ln.hw90"], P_HW, question="Line-by-line DN for hot-water and cooling-water branches.")
U("ur.degasser_steam", "selection", "Degasser steam supply: '4 bar ou 1 bar eff. (à définir)'. The steam inlet is left unconnected until chosen.",
  ["eq.lpf_degasser"], S(2, SEC_3, "Alimentation en 4 bar ou 1 bar eff. (à définir)"), question="Select 4 bar or 1 bar for the degasser.")
U("ur.degasser_hx_medium", "missing_value", "The heating medium and connection of the new make-up water heater (12 → 80 °C) are not stated; its hot side is left open.",
  ["eq.lpf_degasser_hx"], P_DEG, question="Heating medium of the make-up heater.")
U("ur.tge_coil", "conflict",
  "Air-preheating coil: water inlet is limited to 85 °C (sanitary safety) while the process hot-water header is at 90 °C. No tempering/mixing arrangement is specified, so none is added. Only one example coil (TGE) is modelled; the number of coils per tower is not stated.",
  ["eq.bsst_tge_coil", "ln.hw90"], P_AIR, question="How is the 85 °C inlet limit achieved, and how many coils are needed?")
U("ur.lpf_tank_loops", "missing_value",
  "LPF tank heating loops: the circulation pump, fluid and steam supply of the retained steam exchangers are not described; their steam/condensate nozzles are left open.",
  ["eq.lpf_shx_s04", "eq.lpf_shx_an1", "eq.lpf_shx_s05"], P_CUVE)
U("ur.flash_tank", "missing_value",
  "Flash tank: operating pressure and the destination of the 70 °C liquid are not stated; the liquid outlet is left open. The flash-vapour → CMV stage 1 and the inter-stage connections are INTERPRETED from '1 ligne ... sur 3 étages'.",
  ["eq.flash_tank", "eq.cmv_s1", "eq.cmv_s2", "eq.cmv_s3"], P_FLASH, question="Flash-tank liquid destination and pressure; confirm series staging.")
U("ur.spill_control", "missing_value",
  "Spill valves 8 → 4 and 4 → 1 bar: controlled variable, measurement point, setpoint, valve technology and failure position are not stated, so no control loop is created for them.",
  ["pc.pcv_spill_8_4", "pc.pcv_spill_4_1", "cr.spill_8_4", "cr.spill_4_1"], P_PCVS, question="Control philosophy of the overproduction cascade.")
U("ur.boiler", "missing_value", "Gas boiler: capacity, fuel/feed-water/flue connections, PCV technology and failure position are not stated.",
  ["eq.boiler", "pc.pcv_boiler"], P_BOILER)
U("ur.hw_backup", "scope", "'Les réseaux Eau Chaude basculent sur le secours vapeur local' (emergency-exchanger mode): the local steam back-up equipment is not described.",
  ["mode.emergency_hx"], S(3, SEC_4))
U("ur.ultimate_feed", "missing_value", "Ultimate mode: how well water reaches the fermenters (feed line) is not described; only the post-fermenter discharge to DARSE is.",
  ["mode.ultimate", "mf.ferm_out"], S(3, SEC_4))
U("ur.tank_count", "ambiguity", "'RCUA (85°C / 105°C)' is read as a single buffer tank. The PDF lists five buffer tanks (TK-001, TK-002, 70 °C, 90 °C, RCUA).",
  ["eq.tank_rcua"], P_T70, question="One RCUA tank or one per temperature level?")
U("ur.tags", "missing_value", "Equipment tags are given only for P-030..035, ECH-030..032, TK-001/002, K3/MESSO/GEA and the LPF tanks. Heat pumps, 70/90/RCUA tanks, flash tank, CMV stages, boiler and the new exchangers have no tag.",
  ["eq.hp_1a", "eq.hp_1b", "eq.hp_2a", "eq.hp_2b", "eq.tank_70", "eq.tank_90", "eq.tank_rcua", "eq.flash_tank"], S(1, SEC_12))
U("ur.nozzles", "missing_value", "No nozzle numbers or nozzle sizes are given for any equipment (except DN50 on the TGE coil). Nozzle names are schematic.",
  [], S(1, "1. Nouveaux équipements de production"), question="Nozzle schedule.")
U("ur.design_data", "missing_value", "No design pressures, relief devices/sizing, safety thresholds (other than 7.5 bar eff.), valve failure positions, material classes or instrument ranges are given. None are invented.",
  [], S(3, "5. Règles topologiques génératives"))
U("ur.rcua_limits", "scope", "RCUA network battery limits (destination of the 105 °C header and the 85 °C return) are not described; placeholder boundaries are used.",
  ["bc.rcua_out", "bc.rcua_return"], S(1, SEC_12))

if __name__ == "__main__":
    t = Topology.model_validate(topo)
    sha = save_topology(t, OUT)
    print(f"wrote {OUT}  sha256={sha[:12]}…  equipment={len(t.equipment)} components={len(t.components)} lines={len(t.process_lines)}")
