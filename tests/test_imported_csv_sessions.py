"""Offline checks using synthetic data; never connects to CFX-Post."""
import io
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest

from cfxpost_toolkit import ImportedCSVFileConfig, ImportedCSVVariableConfig
from cfxpost_toolkit import ProjectConfig, VisualizationConfig
from cfxpost_toolkit import _engine as engine
from cfxpost_toolkit.gui import ToolkitWizard
from cfxpost_toolkit.sessions import (
    create_imported_csv_import_session,
    create_visualization_sessions,
)


class ImportedCSVSessionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def surface(self, name, variables, *, offset=0, constant=False):
        path = self.root / (name + '.csv')
        headers = ','.join(v.name for v in variables)
        rows = []
        for i, (x, y) in enumerate([(0, 0), (1, 0), (1, 1), (0, 1)]):
            values = ','.join(str(20 if constant else 20 + i + j) for j in range(len(variables)))
            rows.append(f'{x + offset},{y},0,{values}')
        path.write_text('[Data]\nX,Y,Z,' + headers + '\n' + '\n'.join(rows)
                        + '\n[Faces]\n0,1,2\n0,2,3\n', encoding='utf-8')
        return ImportedCSVFileConfig(path, name, variables)

    def generate(self, files, **kwargs):
        settings = VisualizationConfig(
            create_plan_contours=False, create_imported_csv_visualizations=True,
            imported_csv_files=files, **kwargs,
        )
        return create_visualization_sessions(
            ProjectConfig(self.root, direct_visualization_output=True), [], settings,
            case_name='Synthetic Case',
        )

    def test_imports_and_qualified_visuals(self):
        item = self.surface('Surface A', [ImportedCSVVariableConfig(
            'Temperature', create_contour=True, create_histogram=True, create_average=True,
            lower=10, upper=40, number_of_contours=11, histogram_divisions=9,
        )])
        imported = create_imported_csv_import_session([item], self.root).read_text()
        self.assertEqual(imported.count('USER SURFACE: Imported CSV Results Surface A'), 1)
        create, printing, stats = self.generate([item])
        session = create.read_text()
        self.assertIn('Temperature on Imported CSV Results Surface A', session)
        self.assertIn('=areaAve(Temperature on Imported CSV Results Surface A)@Imported CSV Results Surface A', session)
        self.assertIn('/USER SURFACE:Imported CSV Results Surface A', session)
        self.assertEqual(stats['imported_csv_variable_statistics'][('Surface A', 'Temperature')],
                         dict(lower=10, upper=40, number_of_contours=11))
        self.assertEqual(stats['imported_csv_histogram_statistics'][('Surface A', 'Temperature')]['divisions'], 9)
        self.assertIn('Temperature contours at Surface A', printing.read_text())
        self.assertIn('table_average_conditions.csv', printing.read_text())

    def test_shared_average_column_and_missing_cell(self):
        a = self.surface('Surface A', [
            ImportedCSVVariableConfig('Temperature', create_average=True),
            ImportedCSVVariableConfig('Velocity', create_average=True),
        ])
        b = self.surface('Surface B', [ImportedCSVVariableConfig('Temperature', create_average=True)])
        out = io.StringIO()
        engine._write_average_table(out, [], [], [], imported_csv_files=[a, b])
        session = out.getvalue()
        self.assertEqual(session.count('=areaAve(Temperature on'), 2)
        self.assertEqual(session.count('=areaAve(Velocity on'), 1)
        self.assertNotIn('Velocity on Imported CSV Results Surface B', session)
        self.assertEqual(session.count('Temperature'), 3)  # one header and two expressions

    def test_three_average_blocks(self):
        item = self.surface('Surface A', [ImportedCSVVariableConfig('Temperature', create_average=True)])
        out = io.StringIO()
        engine._write_average_table(out, ['Native Surface'], ['Native Volume'], ['Temperature'],
                                    imported_csv_files=[item])
        session = out.getvalue()
        for block in ['Surface Averages', 'Volume Averages', 'Imported Surface Averages']:
            self.assertIn(block, session)
        self.assertIn('=volumeAve(Temperature)', session)

    def test_percentiles_and_camera_include_second_surface(self):
        a = self.surface('Surface A', [ImportedCSVVariableConfig('Temperature', create_contour=True)])
        b = self.surface('Surface B', [ImportedCSVVariableConfig('Temperature', create_contour=True)], offset=100)
        _, _, stats = self.generate([a, b], create_average_table=False)
        bounds = stats['imported_csv_variable_statistics'][('Surface A', 'Temperature')]
        self.assertAlmostEqual(bounds['lower'], 20.15)
        self.assertAlmostEqual(bounds['upper'], 22.85)
        self.assertEqual(set(stats['clip_plane_z']), {'Surface A', 'Surface B'})
        self.assertIn(50.5, stats['camera_pivot'])

    def test_gui_detects_matching_and_differing_variable_sets(self):
        state = SimpleNamespace(imported_csv_items=[
            {'variables': {'Temperature': {}, 'Velocity': {}}},
            {'variables': {'Velocity': {}, 'Temperature': {}}},
        ])
        self.assertTrue(ToolkitWizard._imported_csv_variable_sets_match(state))
        state.imported_csv_items[1]['variables'].pop('Velocity')
        self.assertFalse(ToolkitWizard._imported_csv_variable_sets_match(state))

    def test_average_only_constant_values_need_no_plot_bounds(self):
        item = self.surface('Constant Surface', [ImportedCSVVariableConfig('Temperature', create_average=True)], constant=True)
        create, _, _ = self.generate([item])
        self.assertIn('=areaAve(Temperature on', create.read_text())

    def test_each_imported_contour_has_its_own_defined_legend(self):
        a = self.surface('Surface A', [ImportedCSVVariableConfig('Temperature', create_contour=True)])
        b = self.surface('Surface B', [ImportedCSVVariableConfig('Velocity', create_contour=True)])
        create, _, _ = self.generate([a, b], create_average_table=False)
        session = create.read_text()
        self.assertIn('LEGEND: Legend Imported Temperature at Surface A', session)
        self.assertIn('LEGEND: Legend Imported Velocity at Surface B', session)


if __name__ == '__main__':
    unittest.main()
