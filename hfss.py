from __future__ import division
import atexit
from copy import copy

import tempfile
import numpy
from sympy.parsing import sympy_parser
from pint import UnitRegistry
from win32com.client import Dispatch

ureg = UnitRegistry()
Q = ureg.Quantity

def simplify_arith_expr(expr):
    try:
        out = repr(sympy_parser.parse_expr(str(expr)))
        return out
    except:
        print "Couldn't parse", expr
        raise

def increment_name(base, existing):
    n = 1
    make_name = lambda: base + str(n)
    while make_name() in existing:
        n += 1
    return make_name()

class VariableString(str):
    def __add__(self, other):
        return var("(%s) + (%s)" % (self, other))
    def __radd__(self, other):
        return var("(%s) + (%s)" % (other, self))
    def __sub__(self, other):
        return var("(%s) - (%s)" % (self, other))
    def __rsub__(self, other):
        return var("(%s) - (%s)" % (other, self))
    def __mul__(self, other):
        return var("(%s) * (%s)" % (self, other))
    def __rmul__(self, other):
        return var("(%s) * (%s)" % (other, self))
    def __div__(self, other):
        return var("(%s) / (%s)" % (self, other))
    def __rdiv__(self, other):
        return var("(%s) / (%s)" % (other, self))
    def __truediv__(self, other):
        return var("(%s) / (%s)" % (self, other))
    def __rtruediv__(self, other):
        return var("(%s) / (%s)" % (other, self))
    def __pow__(self, other):
        return var("(%s) ^ (%s)" % (self, other))
    def __rpow__(self, other):
        return var("(%s) ^ (%s)" % (other, self))
    def __neg__(self):
        return var("-(%s)" % self)
    def __abs__(self):
        return var("abs(%s)" % self)

def var(x):
    if isinstance(x, str):
        return VariableString(simplify_arith_expr(x))
    return x

class HfssPropertyObject(object):
    prop_holder = None
    prop_tab = None
    prop_server = None
    def make_prop(self, name, prop_tab=None, prop_server=None):
        prop_tab = self.prop_tab if prop_tab is None else prop_tab
        prop_server = self.prop_server if prop_server is None else prop_server
        def set_prop(value):
            self.prop_holder.SetPropertyValue(prop_tab, prop_server, name, value)

        def get_prop():
            return self.prop_holder.GetPropertyValue(prop_tab, prop_server, name)

        return property(get_prop, set_prop)


class HfssApp(object):
    def __init__(self):
        self._app = Dispatch('AnsoftHfss.HfssScriptInterface')

    def get_app_desktop(self):
        return HfssDesktop(self, self._app.GetAppDesktop())

    def release(self):
        self._app = None

class HfssDesktop(object):
    def __init__(self, app, desktop):
        """
        :type app: HfssApp
        :type desktop: Dispatch
        """
        self.parent = app
        self._desktop = desktop

    def release(self):
        self.parent.release()
        self._desktop = None

    def close_all_windows(self):
        self._desktop.CloseAllWindows()

    def project_count(self):
        return self._desktop.Count()

    def get_active_project(self):
        return HfssProject(self, self._desktop.GetActiveProject())

    def get_projects(self):
        return [HfssProject(self, p) for p in self._desktop.GetProjects()]

    def get_project_names(self):
        return self._desktop.GetProjectList()

    def get_version(self):
        return self._desktop.GetVersion()

    def new_project(self):
        return HfssProject(self, self._desktop.NewProject())

    def open_project(self, path):
        return HfssProject(self, self._desktop.OpenProject(path))

    def set_active_project(self, name):
        self._desktop.SetActiveProject(name)

    @property
    def project_directory(self):
        return self._desktop.GetProjectDirectory()

    @project_directory.setter
    def project_directory(self, path):
        self._desktop.SetProjectDirectory(path)

    @property
    def library_directory(self):
        return self._desktop.GetLibraryDirectory()

    @library_directory.setter
    def library_directory(self, path):
        self._desktop.SetLibraryDirectory(path)

    @property
    def temp_directory(self):
        return self._desktop.GetTempDirectory()

    @temp_directory.setter
    def temp_directory(self, path):
        self._desktop.SetTempDirectory(path)


class HfssProject(object):
    def __init__(self, desktop, project):
        """
        :type desktop: HfssDesktop
        :type project: Dispatch
        """
        self.parent = desktop
        self._project = project
        self.name = project.GetName()

    def release(self):
        self.parent.release()
        self._project = None

    def close(self):
        self._project.Close()

    def make_active(self):
        self.parent.set_active_project(self.name)

    def get_designs(self):
        return [HfssDesign(self, d) for d in self._project.GetDesigns()]

    def save(self, path=None):
        if path is None:
            self._project.Save()
        else:
            self._project.SaveAs(path, True)

    def simulate_all(self):
        self._project.SimulateAll()

    def import_dataset(self, path):
        self._project.ImportDataset(path)

    def get_variables(self):
        return [VariableString(s) for s in self._project.GetVariables()]

    def get_variable_value(self, name):
        return self._project.GetVariableValue(name)

    def create_variable(self, name, value):
        self._project.ChangeProperty(
            ["NAME:AllTabs",
             ["NAME:ProjectVariableTab",
              ["NAME:PropServers", "ProjectVariables"],
              ["Name:NewProps",
               ["NAME:" + name,
                "PropType:=", "VariableProp",
                "UserDef:=", True,
                "Value:=", value]]]])

    def set_variable(self, name, value):
        if name not in self._project.GetVariables():
            self.create_variable(name, value)
        else:
            self._project.SetVariableValue(name, value)
        return VariableString(name)

    def get_path(self):
        return self._project.GetPath()

    def new_design(self, name, type):
        name = increment_name(name, [d.GetName() for d in self._project.GetDesigns()])
        return HfssDesign(self, self._project.InsertDesign("HFSS", name, type, ""))

    def get_design(self, name):
        return HfssDesign(self, self._project.GetDesign(name))

    def get_active_design(self):
        d = self._project.GetActiveDesign()
        if d is None:
            raise EnvironmentError("No Design Active")
        return HfssDesign(self, d)

    def new_dm_design(self, name):
        return self.new_design(name, "DrivenModal")

    def new_em_design(self, name):
        return self.new_design(name, "Eigenmode")


class HfssDesign(object):
    def __init__(self, project, design):
        self.parent = project
        self._design = design
        self.name = design.GetName()
        self.solution_type = design.GetSolutionType()
        if design is None:
            return
        self._setup_module = design.GetModule("AnalysisSetup")
        self._solutions = design.GetModule("Solutions")
        self._fields_calc = design.GetModule("FieldsReporter")
        self._output = design.GetModule("OutputVariable")
        self._boundaries = design.GetModule("BoundarySetup")
        self._modeler = design.SetActiveEditor("3D Modeler")
        self.modeler = HfssModeler(self, self._modeler, self._boundaries)

        atexit.register(self.release)

    def release(self):
        self.parent.release()
        self.modeler.release()
        self._design = None
        self._setup_module = None
        self._solutions = None
        self._fields_calc = None
        self._output = None
        self._boundaries = None
        self._modeler = None

    def copy_to_project(self, project):
        self.parent.CopyDesign(self.name)
        project.make_active()
        project._project.Paste()

    def duplicate(self):
        self.copy_to_project(self.parent)

    def create_dm_setup(self, freq_ghz=1, name=None, max_delta_e=0.1, max_passes=10,
                        min_passes=1, min_converged=1, pct_refinement=30,
                        basis_order=1):

        if name is None:
            name = "Setup"

        name = increment_name(name, self._setup_module.GetSetups())

        self._setup_module.InsertSetup(
            "HfssDriven", [
                "NAME:"+name,
                "Frequency:=", str(freq_ghz)+"GHz",
                "MaxDeltaE:=", max_delta_e,
                "MaximumPasses:=", max_passes,
                "MinimumPasses:=", min_passes,
                "MinimumConvergedPasses:=", min_converged,
                "PercentRefinement:=", pct_refinement,
                "IsEnabled:=", True,
                "BasisOrder:=", basis_order
            ])
        return HfssSetup(self, name)

    def create_em_setup(self, min_freq_ghz=1, n_modes=1, max_delta_f=0.1, max_passes=10,
                        min_passes=1, min_converged=1, pct_refinement=30,
                        basis_order=1):
        name = increment_name("Setup", self._setup_module.GetSetups())
        self._setup_module.InsertSetup(
            "HfssEigen", [
                "NAME:"+name,
                "MinimumFrequency:=", str(min_freq_ghz)+"GHz",
                "NumModes:=", n_modes,
                "MaxDeltaFreq:=", max_delta_f,
                "ConvergeOnRealFreq:=", True,
                "MaximumPasses:=", max_passes,
                "MinimumPasses:=", min_passes,
                "MinimumConvergedPasses:=", min_converged,
                "PercentRefinement:=", pct_refinement,
                "IsEnabled:=", True,
                "BasisOrder:=", basis_order
            ])
        return HfssSetup(self, name)

    def get_nominal_variation(self):
        return self._design.GetNominalVariation()

    def create_variable(self, name, value):
        self._design.ChangeProperty(
            ["NAME:AllTabs",
             ["NAME:LocalVariableTab",
              ["NAME:PropServers", "LocalVariables"],
              ["Name:NewProps",
               ["NAME:" + name,
                "PropType:=", "VariableProp",
                "UserDef:=", True,
                "Value:=", value]]]])

    def set_variable(self, name, value):
        if name not in self._design.GetVariables():
            self.create_variable(name, value)
        else:
            self._design.SetVariableValue(name, value)

        return VariableString(name)


    def get_variable_value(self, name):
        return self._design.GetVariableValue(name)

    def _evaluate_variable_expression(self, expr, units):
        """
        :type expr: str
        :type units: str
        :return: float
        """
        try:
            sexp = sympy_parser.parse_expr(expr)
        except SyntaxError:
            return Q(expr).to(units).magnitude

        sub_exprs = {fs: self.get_variable_value(fs.name) for fs in sexp.free_symbols}
        return float(sexp.subs({fs: self._evaluate_variable_expression(e, units) for fs, e in sub_exprs.items()}))

    def eval_expr(self, expr, units="mm"):
        return str(self._evaluate_variable_expression(expr, units)) + units



class HfssSetup(HfssPropertyObject):
    prop_tab = "HfssTab"

    def __init__(self, design, setup):
        """
        :type design: HfssDesign
        :type setup: Dispatch
        """
        self.parent = self.prop_holder = design
        self.name = setup
        self.solution_name = setup + " : LastAdaptive"
        self.prop_server = "AnalysisSetup:" + setup
        self.passes = self.make_prop("Passes")
        self.pct_refinement = self.make_prop("Percent Refinement")
        self.basis_order = self.make_prop("Basis Order")

    def analyze(self):
        self.parent._design.Analyze(self.name)

    def get_convergence(self, variation=""):
        fn = tempfile.mktemp()
        self.parent._design.ExportConvergence(self.name, variation, fn, False)
        return numpy.loadtxt(fn)

    def get_mesh_stats(self, variation=""):
        fn = tempfile.mktemp()
        self.parent._design.ExportMeshStats(self.name, variation, fn, False)
        return numpy.loadtxt(fn)

    def get_profile(self, variation=""):
        fn = tempfile.mktemp()
        self.parent._design.ExportProfile(self.name, variation, fn, False)
        return numpy.loadtxt(fn)

    def get_solutions(self):
        return HfssDesignSolutions(self, self.parent._solutions)


class HfssDMSetup(HfssSetup):
    def __init__(self, design, setup):
        super(HfssDMSetup, self).__init__(design, setup)
        self.solution_freq = self.make_prop("Solution Freq")
        self.delta_e = self.make_prop("Delta Energy")

class HfssEMSetup(HfssSetup):
    def __init__(self, design, setup):
        super(HfssEMSetup, self).__init__(design, setup)
        self.min_freq = self.make_prop("Min Freq")
        self.n_modes = self.make_prop("Modes")
        self.delta_f = self.make_prop("Delta F")

class HfssDesignSolutions(object):
    def __init__(self, setup, solutions):
        self.parent = setup
        self._solutions = solutions

class HfssEMDesignSolutions(HfssDesignSolutions):
    def eigenmodes(self):
        fn = tempfile.mktemp()
        self._solutions.ExportEigenmodes(self.parent.name, "", fn)
        return numpy.loadtxt(fn)

    def set_mode(self, n, phase):
        n_modes = self.parent.n_modes
        self._solutions.EditSources(
            "TotalFields",
            ["NAME:SourceNames", "EigenMode"],
            ["NAME:Modes", n_modes],
            ["NAME:Magnitudes"] + [1 if i + 1 == n else 0 for i in range(n_modes)],
            ["NAME:Phases"] + [phase if i + 1 == n else 0 for i in range(n_modes)],
            ["NAME:Terminated"], ["NAME:Impedances"]
        )

class HfssDMDesignSolutions(HfssDesignSolutions):
    def get_network_data(self, formats):
        if isinstance(formats, str):
            formats = formats.split(",")

        fmts_lists = {'S': [], 'Y': [], 'Z': []}

        for f in formats:
            f = f.upper()
            fmts_lists[f[0]].append((int(f[1]), int(f[2])))

        for data_type, list in fmts_lists.items():
            if list:
                fn = tempfile.mktemp()
                self._solutions.ExportNetworkData(
                    [],  self.parent,
                      2, fn, ["all"], False, 0,
                      data_type, "", "1"
                )

class HfssModeler(object):
    def __init__(self, design, modeler, boundaries):
        """
        :type design: HfssDesign
        """
        self.parent = design
        self._modeler = modeler
        self._boundaries = boundaries

    def release(self):
        self._modeler = None
        self._boundaries = None

    def set_units(self, units, rescale=True):
        self._modeler.SetModelUnits(["NAME:Units Parameter", "Units:=", units, "Rescale:=", rescale])

    def _attributes_array(self, name=None, nonmodel=False, color=None, transparency=0.9, material=None):
        arr = ["NAME:Attributes"]
        if name is not None:
            arr.extend(["Name:=", name])
        if nonmodel:
            arr.extend(["Flags:=", "NonModel"])

        if color is not None:
            arr.extend(["Color:=", "(%d %d %d)" % color])
        if transparency is not None:
            arr.extend(["Transparency:=", transparency])
        if material is not None:
            arr.extend(["MaterialName:=", material])
        return arr

    def _selections_array(self, *names):
        return ["NAME:Selections", "Selections:=", ",".join(names)]

    def draw_box_corner(self, pos, size, **kwargs):
        name = self._modeler.CreateBox(
            ["NAME:BoxParameters",
             "XPosition:=", pos[0],
             "YPosition:=", pos[1],
             "ZPosition:=", pos[2],
             "XSize:=", size[0],
             "YSize:=", size[1],
             "ZSize:=", size[2]],
            self._attributes_array(**kwargs)
        )
        return Box(name, self, pos, size)

    def draw_box_center(self, pos, size, **kwargs):
        corner_pos = [var(p) - var(s)/2 for p, s in zip(pos, size)]
        return self.draw_box_corner(corner_pos, size, **kwargs)

    def draw_rect_corner(self, pos, x_size=0, y_size=0, z_size=0, **kwargs):
        size = [x_size, y_size, z_size]
        assert 0 in size
        axis = "XYZ"[size.index(0)]
        w_idx, h_idx = {
            'X': (1, 2),
            'Y': (2, 0),
            'Z': (0, 1)
        }[axis]

        name = self._modeler.CreateRectangle(
            ["NAME:RectangleParameters",
             "XStart:=", pos[0],
             "YStart:=", pos[1],
             "ZStart:=", pos[2],
             "Width:=", size[w_idx],
             "Height:=", size[h_idx],
             "WhichAxis:=", axis],
            self._attributes_array(**kwargs)
        )
        return Rect(name, self, pos, size)

    def draw_rect_center(self, pos, x_size=0, y_size=0, z_size=0, **kwargs):
        corner_pos = [var(p) - var(s)/2 for p, s in zip(pos, [x_size, y_size, z_size])]
        return self.draw_rect_corner(corner_pos, x_size, y_size, z_size, **kwargs)


    def draw_cylinder(self, pos, radius, height, axis, **kwargs):
        assert axis in "XYZ"
        return self._modeler.CreateCylinder(
            ["NAME:CylinderParameters",
             "XCenter:=", pos[0],
             "YCenter:=", pos[1],
             "ZCenter:=", pos[2],
             "Radius:=", radius,
             "Height:=", height,
             "WhichAxis:=", axis,
             "NumSides:=", 0],
            self._attributes_array(**kwargs))

    def draw_cylinder_center(self, pos, radius, height, axis, **kwargs):
        axis_idx = ["X", "Y", "Z"].index(axis)
        edge_pos = copy(pos)
        edge_pos[axis_idx] = var(pos[axis_idx]) - var(height)/2
        return self.draw_cylinder(edge_pos, radius, height, axis, **kwargs)

    def unite(self, names, keep_originals=False):
        self._modeler.Unite(
            self._selections_array(*names),
            ["NAME:UniteParameters", "KeepOriginals:=", keep_originals]
        )
        return names[0]

    def intersect(self, names, keep_originals=False):
        self._modeler.Intersect(
            self._selections_array(*names),
            ["NAME:IntersectParameters", "KeepOriginals:=", keep_originals]
        )
        return names[0]

    def translate(self, name, vector):
        self._modeler.Move(
            self._selections_array(name),
            ["NAME:TranslateParameters",
             "TranslateVectorX:=", vector[0],
             "TranslateVectorY:=", vector[1],
             "TranslateVectorZ:=", vector[2]]
        )

    def make_perfect_E(self, *objects):
        name = increment_name("PerfE", self._boundaries.GetBoundaries())
        self._boundaries.AssignPerfectE(["NAME:"+name, "Objects:=", objects, "InfGroundPlane:=", False])

    def _make_lumped_rlc(self, r, l, c, start, end, obj_arr, name="LumpLRC"):
        name = increment_name(name, self._boundaries.GetBoundaries())
        params = ["NAME:"+name]
        params += obj_arr
        params.append(["NAME:CurrentLine", "Start:=", start, "End:=", end])
        params += ["UseResist:=", r != 0, "Resistance:=", r,
                   "UseInduct:=", l != 0, "Inductance:=", l,
                   "UseCap:=", c != 0, "Capacitance:=", c]
        self._boundaries.AssignLumpedRLC(params)

    def _make_lumped_port(self, start, end, obj_arr, z0="50ohm", name="LumpPort"):
        name = increment_name(name, self._boundaries.GetBoundaries())
        params = ["NAME:"+name]
        params += obj_arr
        params += ["RenormalizeAllTerminals:=", True, "DoDeembed:=", False,
                   ["NAME:Modes", ["NAME:Mode1", "ModeNum:=", 1, "UseIntLine:=", True,
                                   ["NAME:IntLine", "Start:=", start, "End:=", end],
                                   "CharImp:=", "Zpi", "AlignmentGroup:=", 0, "RenormImp:=", "50ohm"]],
                   "ShowReporterFilter:=", False, "ReporterFilter:=", [True],
                   "FullResistance:=", "50ohm", "FullReactance:=", "0ohm"]

        self._boundaries.AssignLumpedPort(params)


    def get_face_ids(self, obj):
        return self. _modeler.GetFaceIDs(obj)

    def eval_expr(self, expr, units="mm"):
        return self.parent.eval_expr(expr, units)


class ModelEntity(str, HfssPropertyObject):
    prop_tab = "Geometry3DCmdTab"
    model_command = None
    def __new__(self, val, *args, **kwargs):
        return str.__new__(self, val)

    def __init__(self, val, modeler):
        """
        :type val: str
        :type modeler: HfssModeler
        """
        super(ModelEntity, self).__init__(val)
        self.modeler = modeler
        self.prop_server = self + ":" + self.model_command + ":1"
        self.transparency = self.make_prop("Transparent", prop_tab="Geometry3DAttributeTab", prop_server=self)
        self.material = self.make_prop("Material", prop_tab="Geometry3DAttributeTab", prop_server=self)
        self.coordinate_system = self.make_prop("Coordinate System")


class Box(ModelEntity):
    model_command = "CreateBox"
    def __init__(self, name, modeler, corner, size):
        super(Box, self).__init__(name, modeler)
        self.modeler = self.prop_holder = modeler
        self.position = self.make_prop("Position")
        self.x_size = self.make_prop("XSize")
        self.y_size = self.make_prop("YSize")
        self.z_size = self.make_prop("ZSize")
        self.corner = corner
        self.size = size
        self.center = [c + s/2 for c, s in zip(corner, size)]
        faces = modeler.get_face_ids(self)
        self.z_back_face, self.z_front_face = faces[0], faces[1]
        self.y_back_face, self.y_front_face = faces[2], faces[4]
        self.x_back_face, self.x_front_face = faces[3], faces[5]

class Rect(ModelEntity):
    model_command = "CreateRectangle"
    def __init__(self, name, modeler, corner, size):
        super(Rect, self).__init__(name, modeler)
        self.corner = corner
        self.size = size
        self.center = [c + s/2 if s else c for c, s in zip(corner, size)]

    def make_center_line(self, axis):
        axis_idx = ["x", "y", "z"].index(axis.lower())
        start = [c for c in self.center]
        start[axis_idx] -= self.size[axis_idx]/2
        start = [self.modeler.eval_expr(s) for s in start]
        end = [c for c in self.center]
        end[axis_idx] += self.size[axis_idx]/2
        end = [self.modeler.eval_expr(s) for s in end]
        return start, end

    def make_rlc_boundary(self, axis, r=0, l=0, c=0, name="LumpLRC"):
        start, end = self.make_center_line(axis)
        self.modeler._make_lumped_rlc(r, l, c, start, end, ["Objects:=", [self]], name=name)

    def make_lumped_port(self, axis, z0="50ohm", name="LumpPort"):
        start, end = self.make_center_line(axis)
        self.modeler._make_lumped_port(start, end, ["Objects:=", [self]], z0=z0, name=name)


class HfssFieldsCalc(object):
    def __init__(self):
        self.Mag_E = NamedCalcObject("Mag_E", self)
        self.Mag_H = NamedCalcObject("Mag_H", self)
        self.Mag_Jsurf = NamedCalcObject("Mag_Jsurf", self)
        self.Mag_Jvol = NamedCalcObject("Mag_Jvol", self)
        self.Vector_E = NamedCalcObject("Vector_E", self)
        self.Vector_H = NamedCalcObject("Vector_H", self)
        self.Vector_Jsurf = NamedCalcObject("Vector_Jsurf", self)
        self.Vector_Jvol = NamedCalcObject("Vector_Jvol", self)
        self.ComplexMag_E = NamedCalcObject("ComplexMag_E", self)
        self.ComplexMag_H = NamedCalcObject("ComplexMag_H", self)
        self.ComplexMag_Jsurf = NamedCalcObject("ComplexMag_Jsurf", self)
        self.ComplexMag_Jvol = NamedCalcObject("ComplexMag_Jvol", self)


class CalcObject(object):
    def __init__(self, stack, calc_module):
        self.stack = stack
        self.calc_module = calc_module

    def _bin_op(self, other, op):
        if isinstance(other, (int, float)):
            other = ConstantCalcObject(other, self.calc_module)

        stack = self.stack + other.stack
        stack.append(("CalcOp", op))
        return CalcObject(stack, self.calc_module)

    def _unary_op(self, op):
        stack = self.stack[:]
        stack.append(("CalcOp", op))
        return CalcObject(stack, self.calc_module)

    def __add__(self, other):
        return self._bin_op(other, "+")

    def __radd__(self, other):
        return self + other

    def __sub__(self, other):
        return self._bin_op(other, "-")

    def __rsub__(self, other):
        return (-self) + other

    def __mul__(self, other):
        return self._bin_op(other, "*")

    def __rmul__(self, other):
        return self*other

    def __div__(self, other):
        return self._bin_op(other, "/")

    def __rdiv__(self, other):
        other = ConstantCalcObject(other, self.calc_module)
        return other/self

    def __pow__(self, other):
        return self._bin_op(other, "Pow")

    def __neg__(self):
        return self._unary_op("Neg")

    def __abs__(self):
        return self._unary_op("Abs")

    def scalar_x(self):
        return self._unary_op("ScalarX")

    def scalar_y(self):
        return self._unary_op("ScalarY")

    def scalar_z(self):
        return self._unary_op("ScalarZ")

    def real(self):
        return self._unary_op("Real")

    def imag(self):
        return self._unary_op("Imag")

    def _integrate(self, name, type):
        stack = self.stack + [(type, name), ("CalcOp", "Integrate")]
        return CalcObject(stack, self.calc_module)

    def integrate_line(self, name):
        return self._integrate(name, "EnterLine")

    def integrate_surf(self, name="AllObjects"):
        return self._integrate(name, "EnterSurf")

    def integrate_vol(self, name="AllObjects"):
        return self._integrate(name, "EnterVol")

    def write_stack(self):
        for fn, arg in self.stack:
            getattr(self.calc_module, fn)(arg)

    def save_as(self, name):
        self.write_stack()
        self.calc_module.AddNamedExpr(name)
        return NamedCalcObject(name, self.calc_module)

    def evaluate(self, n_mode=1, phase=0):
        self.write_stack()
        self.calc_module.set_mode(n_mode, 0)
        setup_name = self.calc_module.default_setup_name
        vars = ["Phase:=", str(int(phase)) + "deg"]
        self.calc_module.ClcEval(setup_name, vars)
        return float(self.calc_module.GetTopEntryValue(setup_name, vars)[0])


class NamedCalcObject(CalcObject):
    def __init__(self, name, calc_module):
        stack = [("CopyNamedExprToStack", name)]
        super(NamedCalcObject, self).__init__(stack, calc_module)


class ConstantCalcObject(CalcObject):
    def __init__(self, num, calc_module):
        stack = [("EnterScalar", num)]
        super(ConstantCalcObject, self).__init__(stack, calc_module)

def get_active_project():
    app = HfssApp()
    desktop = app.get_app_desktop()
    return desktop.get_active_project()

def get_active_design():
    project = get_active_project()
    return project.get_active_design()