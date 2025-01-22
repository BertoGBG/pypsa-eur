
# import necessary Python modules
from atlite.gis import ExclusionContainer
from atlite.gis import shape_availability
from rasterio.plot import show
import matplotlib.pyplot as plt
import geopandas
import pandas 
import atlite
import logging




def build_potentials(network_geojson, corine_dataset, bioclimate_dataset, component, csv_file, png_file, log):

    # load network geojson file representing the PyPSA-Eur network
    nodes_geojson = geopandas.read_file(network_geojson).set_index("name")
    node_data = {}

    excluder_EWtotal = ExclusionContainer(crs = 3035, res=250)
    for comp in component:
         # configure log mechanism
        if log is True:
            logging.basicConfig(level = snakemake.config["logging"]["level"])
            logger = logging.getLogger(__name__)
            logger.info("Calculate %s potentials" % comp)
        # select CORINE Land Cover (CLC) codes (specified in the config yaml file)
        excluder = ExclusionContainer(crs = 3035, res=250)
        excluder.add_raster(corine_dataset, codes = snakemake.config["EW"][comp]["corine"], invert = True, crs = 3035)
        excluder.add_raster(bioclimate_dataset, codes = snakemake.config["EW"][comp]["climate"], invert = True, crs = 3035)
        cell_area = excluder.res**2

        excluder_EWtotal.add_raster(excluder)


        # calculate potential per node
        for node in nodes_geojson.index:
            shape = nodes_geojson.to_crs(excluder.crs).loc[[node]].geometry
            band, transform = shape_availability(shape, excluder)
            selected_cells = band.sum() * cell_area / 1e6   # in sqkm
            potential = selected_cells * snakemake.config["EW"][comp]["potential_per_sqkm"]
            if node not in node_data:
                node_data[node] = {"node": node}
            node_data[node]["potential_" + comp] = potential
            #print("Node=%s" % node)
            #print("Area (km2)=%.2f" % (shape.geometry.area.sum() / 1e6))
            #print("Potential=%.2f" % potential)

    df = pandas.DataFrame.from_dict(node_data, orient="index").reset_index(drop=True)

    # configure log mechanism
    if log is True:
        logging.basicConfig(level = snakemake.config["logging"]["level"])
        logger = logging.getLogger(__name__)
        
    # save potentials into a CSV file
    if csv_file is not None:
        if log is True:
            logger.info("Save %s potentials into CSV file" % component)
        df.set_index("node", inplace = True)
        df.to_csv(csv_file)


    # save potentials into a PNG file
    if png_file is not None:
        if log is True:
            logger.info("Save %s potentials into PNG file" % component)
        shape = nodes_geojson.to_crs(excluder_EWtotal.crs).geometry
        band, transform = shape_availability(shape, excluder)
        fig, ax = plt.subplots(figsize = (20, 23))
        ax.set_axis_off()
        shape.plot(ax = ax, color = "none")
        show(band, transform = transform, cmap = "Greens", ax = ax)
        plt.savefig(png_file)



if __name__ == "__main__":


    # mock Snakemake in case Python module is called from a terminal
    if "snakemake" not in globals():
        from _helpers import mock_snakemake

        snakemake = mock_snakemake("build_potentials")
        

    # build and save potentials into CSV and PNG files
    build_potentials(snakemake.input["network_geojson"], snakemake.input["corine_dataset"],snakemake.input["bioclimate_dataset"],["EW_hot","EW_temperate"],snakemake.output["csv_file"], snakemake.output["png_file"],True)
    