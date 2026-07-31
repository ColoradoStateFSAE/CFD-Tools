"""
Half Car -- meshing journal
===========================
Derived from a Fluent 2026 R1 recording (7_30_meshing.jou), with the recorded
constants replaced by double-brace placeholders. Argument names and nesting are
exactly as Fluent wrote them; do not rename them by hand.

Uses the classic workflow.TaskObject[...] API, which is what PyFluent journal
recording emits for meshing workflows.

Bound by core.journal_runner:  workflow, meshing, watertight, config, log

Stops after Improve Volume Mesh. The suite writes the mesh file itself, since
it owns the output path.
"""

# ─────────────────────────────────────────────────────────────────────────────
#@ 2 | Setting units to SI
# ─────────────────────────────────────────────────────────────────────────────

meshing.GlobalSettings.LengthUnit.set_state(r"m")
meshing.GlobalSettings.AreaUnit.set_state(r"m^2")
meshing.GlobalSettings.VolumeUnit.set_state(r"m^3")


# ─────────────────────────────────────────────────────────────────────────────
#@ 5 | Importing geometry
# ─────────────────────────────────────────────────────────────────────────────

workflow.TaskObject["Import Geometry"].Arguments.set_state({
    "FileName":   {{GEOMETRY_PATH}},
    "LengthUnit": "m",
})
workflow.TaskObject["Import Geometry"].Execute()


# ─────────────────────────────────────────────────────────────────────────────
#@ 10 | Creating the local refinement task
# ─────────────────────────────────────────────────────────────────────────────

workflow.TaskObject["Import Geometry"].InsertNextTask(
    CommandName=r"CreateLocalRefinementRegions"
)

# Fluent requires the whole argument tree on every set_state call, including
# branches this box does not use (cylinder, offset, geometry tools). These
# defaults come straight from the recording.
_CYLINDER = {
    "HeightBackInc": 0, "HeightFrontInc": 0,
    "Radius1": 0.475, "Radius2": 1.9,
    "X-Offset": 0, "X1": 0, "X2": 9.5,
    "Y-Offset": 0, "Y1": 0, "Y2": 0,
    "Z-Offset": 0, "Z1": 0, "Z2": 0,
}
_GEOM_TOOLS = {
    "BoxCenterX": 0, "BoxCenterY": 0, "BoxCenterZ": 0,
    "BoxXLength": 0, "BoxYLength": 0, "BoxZLength": 0,
    "CylinderRadius1": 0, "CylinderRadius2": 0,
    "CylinderX1": 0, "CylinderX2": 0,
    "CylinderY1": 0, "CylinderY2": 0,
    "CylinderZ1": 0, "CylinderZ2": 0,
}
_OFFSET = {
    "AspectRatio": 5, "BoundaryLayerHeight": 2.56, "BoundaryLayerLevels": 1,
    "CrossWakeGrowthFactor": 1.1, "DefeaturingSize": 0.16, "FirstHeight": 0.01,
    "FlipDirection": False, "FlowDirection": r"X", "LastRatioPercentage": 20,
    "MptMethodType": r"Automatic", "NumberOfLayers": 4,
    "OffsetMethodType": r"uniform", "Rate": 1.2, "ShowCoordinates": True,
    "WakeGrowthFactor": 2, "WakeLevels": 1, "X": 0, "Y": 0, "Z": 0,
}
_AXIS = {"X-Comp": 0, "Y-Comp": 0, "Z-Comp": 1}


def _coordinate_box(name, size, x_min, x_max, y_min, y_max, z_min, z_max):
    """
    Refinement box in absolute coordinates -- Tables 1-3.

    SelectionType is 'label' but LabelSelectionList is deliberately omitted:
    the box is positioned in absolute space, so it applies to whatever falls
    inside it.
    """
    task = workflow.TaskObject["Create Local Refinement Regions"]
    task.Arguments.set_state({
        "Axis": _AXIS,
        "BOIMaxSize": size,
        "BOISizeName": r"boi_1",
        "BoundingBoxObject": {
            "SizeRelativeLength": r"Directly specify coordinates",
            "Xmax": x_max, "XmaxRatio": 0.1,
            "Xmin": x_min, "XminRatio": 0.1,
            "Ymax": y_max, "YmaxRatio": 0.1,
            "Ymin": y_min, "YminRatio": 0.1,
            "Zmax": z_max, "ZmaxRatio": 0.1,
            "Zmin": z_min, "ZminRatio": 0.1,
        },
        "CreationMethod": r"Box",
        "CylinderLength": 9.5,
        "CylinderMethod": r"Vector and Length",
        "CylinderObject": _CYLINDER,
        "GeometryToolsProperties": _GEOM_TOOLS,
        "OffsetObject": _OFFSET,
        "RefinementRegionsName": name,
        "SelectionType": r"label",
        "VolumeFill": r"hexcore",
    })
    task.AddChildAndUpdate(DeferUpdate=False, RetainValues=True)
    log.info(f"  {name}: size {size} m  "
             f"X[{x_min:.3f}, {x_max:.3f}]  "
             f"Y[{y_min:.3f}, {y_max:.3f}]  "
             f"Z[{z_min:.3f}, {z_max:.3f}]")


def _wheel_box(name, size, labels):
    """
    Wheel refinement box -- Table 4.

    Bounds are ratios of the selected body, so LabelSelectionList is required:
    without it there is nothing to be relative to.
    """
    task = workflow.TaskObject["Create Local Refinement Regions"]
    task.Arguments.set_state({
        "Axis": _AXIS,
        "BOIMaxSize": size,
        "BOISizeName": r"boi_1",
        "BoundingBoxObject": {
            "SizeRelativeLength": r"Ratio relative to geometry size",
            "XmaxRatio": 1.0, "XminRatio": 0.1,
            "YmaxRatio": 0.1, "YminRatio": 0.0,
            "ZmaxRatio": 0.1, "ZminRatio": 0.1,
        },
        "CreationMethod": r"Box",
        "CylinderLength": 9.5,
        "CylinderMethod": r"Vector and Length",
        "CylinderObject": _CYLINDER,
        "GeometryToolsProperties": _GEOM_TOOLS,
        "LabelSelectionList": labels,
        "OffsetObject": _OFFSET,
        "RefinementRegionsName": name,
        "SelectionType": r"label",
        "VolumeFill": r"hexcore",
    })
    task.AddChildAndUpdate(DeferUpdate=False, RetainValues=True)
    log.info(f"  {name}: size {size} m  relative to {labels}")


# ─────────────────────────────────────────────────────────────────────────────
#@ 14 | Near field refinement box
# ─────────────────────────────────────────────────────────────────────────────

_coordinate_box(
    r"local-refinement-nearfield", {{NEAR_SIZE}},
    {{NEAR_X_MIN}}, {{NEAR_X_MAX}},
    {{NEAR_Y_MIN}}, {{NEAR_Y_MAX}},
    {{NEAR_Z_MIN}}, {{NEAR_Z_MAX}},
)


# ─────────────────────────────────────────────────────────────────────────────
#@ 18 | Mid field refinement box
# ─────────────────────────────────────────────────────────────────────────────

_coordinate_box(
    r"local-refinement-midfield", {{MID_SIZE}},
    {{MID_X_MIN}}, {{MID_X_MAX}},
    {{MID_Y_MIN}}, {{MID_Y_MAX}},
    {{MID_Z_MIN}}, {{MID_Z_MAX}},
)


# ─────────────────────────────────────────────────────────────────────────────
#@ 22 | Far field refinement box
# ─────────────────────────────────────────────────────────────────────────────

_coordinate_box(
    r"local-refinement-farfield", {{FAR_SIZE}},
    {{FAR_X_MIN}}, {{FAR_X_MAX}},
    {{FAR_Y_MIN}}, {{FAR_Y_MAX}},
    {{FAR_Z_MIN}}, {{FAR_Z_MAX}},
)


# ─────────────────────────────────────────────────────────────────────────────
#@ 26 | Wheel refinement boxes
# ─────────────────────────────────────────────────────────────────────────────

# Half car carries one wheel per axle: fw/fwb front, rw/rwb rear.
_wheel_box(r"local-refinement-frontwheel", {{WHEEL_BOX_SIZE}},
           {{WHEEL_LABELS_FRONT}})
_wheel_box(r"local-refinement-rearwheel",  {{WHEEL_BOX_SIZE}},
           {{WHEEL_LABELS_REAR}})


# ─────────────────────────────────────────────────────────────────────────────
#@ 30 | Local sizing: chassis and suspension
# ─────────────────────────────────────────────────────────────────────────────

# Curvature controls, not plain face sizes -- the curvature normal angle is
# what refines curved surfaces. Note 'faces and edges' uses spaces here, while
# the surface mesh task uses 'faces-and-edges' with hyphens.
workflow.TaskObject["Add Local Sizing"].Arguments.set_state({
    "AddChild": r"yes",
    "BOICellsPerGap": 1,
    "BOIControlName": r"curvature_stuff",
    "BOICurvatureNormalAngle": 12,
    "BOIExecution": r"Curvature",
    "BOIFaceLabelList": {{STUFF_LABELS}},
    "BOIGrowthRate": 1.2,
    "BOIMaxSize": 0.064,
    "BOIMinSize": 0.001,
    "BOIScopeTo": r"faces and edges",
    "BOIZoneorLabel": r"label",
})
workflow.TaskObject["Add Local Sizing"].AddChildAndUpdate(
    DeferUpdate=False, RetainValues=True
)


# ─────────────────────────────────────────────────────────────────────────────
#@ 34 | Local sizing: aero surfaces
# ─────────────────────────────────────────────────────────────────────────────

workflow.TaskObject["Add Local Sizing"].Arguments.set_state({
    "AddChild": r"yes",
    "BOICellsPerGap": 1,
    "BOIControlName": r"curvature_aero",
    "BOICurvatureNormalAngle": 9,
    "BOIExecution": r"Curvature",
    "BOIFaceLabelList": {{AERO_LABELS}},
    "BOIGrowthRate": 1.2,
    "BOIMaxSize": 0.008,
    "BOIMinSize": 0.0005,
    "BOIScopeTo": r"faces and edges",
    "BOIZoneorLabel": r"label",
    "DrawSizeControl": True,
})
workflow.TaskObject["Add Local Sizing"].AddChildAndUpdate(
    DeferUpdate=False, RetainValues=True
)


# ─────────────────────────────────────────────────────────────────────────────
#@ 38 | Local sizing: wheels
# ─────────────────────────────────────────────────────────────────────────────

# Wheels scope to faces only, not faces and edges.
workflow.TaskObject["Add Local Sizing"].Arguments.set_state({
    "AddChild": r"yes",
    "BOICellsPerGap": 1,
    "BOIControlName": r"curvature_wheels",
    "BOICurvatureNormalAngle": 18,
    "BOIExecution": r"Curvature",
    "BOIFaceLabelList": {{WHEEL_LABELS_ALL}},
    "BOIGrowthRate": 1.2,
    "BOIMaxSize": 0.032,
    "BOIMinSize": 0.0005,
    "BOIScopeTo": r"faces",
    "BOIZoneorLabel": r"label",
    "DrawSizeControl": True,
})
workflow.TaskObject["Add Local Sizing"].AddChildAndUpdate(
    DeferUpdate=False, RetainValues=True
)


# ─────────────────────────────────────────────────────────────────────────────
#@ 45 | Generating surface mesh
# ─────────────────────────────────────────────────────────────────────────────

workflow.TaskObject["Generate the Surface Mesh"].Arguments.set_state({
    "CFDSurfaceMeshControls": {
        "CellsPerGap": 3,
        "DrawSizeControl": False,
        "MaxSize": {{SURFACE_MAX}},
        "MinSize": {{SURFACE_MIN}},
        "ScopeProximityTo": r"faces-and-edges",
    },
})
workflow.TaskObject["Generate the Surface Mesh"].Execute()


# ─────────────────────────────────────────────────────────────────────────────
#@ 58 | Improving surface mesh
# ─────────────────────────────────────────────────────────────────────────────

workflow.TaskObject["Generate the Surface Mesh"].InsertNextTask(
    CommandName=r"ImproveSurfaceMesh"
)
workflow.TaskObject["Improve Surface Mesh"].Arguments.set_state({
    "FaceQualityLimit": 0.7,
})
workflow.TaskObject["Improve Surface Mesh"].Execute()


# ─────────────────────────────────────────────────────────────────────────────
#@ 62 | Describing geometry
# ─────────────────────────────────────────────────────────────────────────────

workflow.TaskObject["Describe Geometry"].Arguments.set_state({
    "NonConformal": r"No",
    "SetupType": r"The geometry consists of only fluid regions with no voids",
    # Doc Step 7: do NOT convert fluid-fluid walls to internal.
    "WallToInternal": r"No",
})
workflow.TaskObject["Describe Geometry"].UpdateChildTasks(
    Arguments={"v1": True}, SetupTypeChanged=True
)
workflow.TaskObject["Describe Geometry"].Execute()


# ─────────────────────────────────────────────────────────────────────────────
#@ 66 | Updating boundaries and regions
# ─────────────────────────────────────────────────────────────────────────────

workflow.TaskObject["Update Boundaries"].Execute()
workflow.TaskObject["Update Regions"].Execute()


# ─────────────────────────────────────────────────────────────────────────────
#@ 70 | Adding boundary layers
# ─────────────────────────────────────────────────────────────────────────────

# Grown on the aero surfaces, the wheels and the ground.
workflow.TaskObject["Add Boundary Layers"].Arguments.set_state({
    "BLControlName": r"last-ratio_1",
    "FaceScope": {"GrowOn": r"selected-zones"},
    "FirstHeight": {{BL_FIRST_HEIGHT}},
    "LocalPrismPreferences": {"Continuous": r"Continuous"},
    "NumberOfLayers": {{BL_LAYERS}},
    "OffsetMethodType": r"last-ratio",
    "ZoneSelectionList": {{BL_ZONES}},
})
workflow.TaskObject["Add Boundary Layers"].AddChildAndUpdate(
    DeferUpdate=False, RetainValues=True
)


# ─────────────────────────────────────────────────────────────────────────────
#@ 75 | Generating volume mesh
# ─────────────────────────────────────────────────────────────────────────────

# MeshSolidRegions False: any region that is not the enclosure stays unmeshed.
workflow.TaskObject["Generate the Volume Mesh"].Arguments.set_state({
    "MeshSolidRegions": False,
    "VolumeFill": r"poly-hexcore",
    "VolumeFillControls": {
        "HexMaxCellLength": {{VOLUME_MAX}},
        "HexMinCellLength": {{VOLUME_MIN}},
    },
})
workflow.TaskObject["Generate the Volume Mesh"].Execute()


# ─────────────────────────────────────────────────────────────────────────────
#@ 92 | Improving volume mesh
# ─────────────────────────────────────────────────────────────────────────────

workflow.TaskObject["Generate the Volume Mesh"].InsertNextTask(
    CommandName=r"ImproveVolumeMesh"
)
workflow.TaskObject["Improve Volume Mesh"].Arguments.set_state({
    "AddMultipleQualityMethods": r"No",
    "CellQualityLimit": 0.2,
    "QualityMethod": r"Orthogonal",
    "VMImprovePreferences": {
        "ShowVMImprovePreferences": False,
        "VIQualityIterations": 5,
        "VIQualityMinAngle": 0,
        "VIgnoreFeature": r"yes",
    },
})
workflow.TaskObject["Improve Volume Mesh"].Execute()

log.info("  Meshing journal complete -- suite will write the mesh file")