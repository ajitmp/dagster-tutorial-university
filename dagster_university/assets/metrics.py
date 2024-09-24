from dagster import asset, AssetExecutionContext

import plotly.express as px
import plotly.io as pio
import pandas as pd
import geopandas as gpd
from datetime import datetime, timedelta
from dagster_duckdb import DuckDBResource
from ..partitions import weekly_partition

import duckdb
import os

from . import constants


@asset(
    deps=["taxi_trips", "taxi_zones"]
)
def manhattan_stats(database: DuckDBResource) -> None:
    query = """
        select
            zones.zone,
            zones.borough,
            zones.geometry,
            count(1) as num_trips,
        from trips
        left join zones on trips.pickup_zone_id = zones.zone_id
        where borough = 'Manhattan' and geometry is not null
        group by zone, borough, geometry
    """

    # conn = duckdb.connect(os.getenv("DUCKDB_DATABASE"))
    # trips_by_zone = conn.execute(query).fetch_df()
    with database.get_connection() as conn:
        trips_by_zone = conn.execute(query).fetch_df()

    trips_by_zone["geometry"] = gpd.GeoSeries.from_wkt(trips_by_zone["geometry"])
    trips_by_zone = gpd.GeoDataFrame(trips_by_zone)

    with open(constants.MANHATTAN_STATS_FILE_PATH, 'w') as output_file:
        output_file.write(trips_by_zone.to_json())


@asset(
    deps=["manhattan_stats"],
)
def manhattan_map() -> None:
    trips_by_zone = gpd.read_file(constants.MANHATTAN_STATS_FILE_PATH)

    fig = px.choropleth_mapbox(trips_by_zone,
        geojson=trips_by_zone.geometry.__geo_interface__,
        locations=trips_by_zone.index,
        color='num_trips',
        color_continuous_scale='Plasma',
        mapbox_style='carto-positron',
        center={'lat': 40.758, 'lon': -73.985},
        zoom=11,
        opacity=0.7,
        labels={'num_trips': 'Number of Trips'}
    )

    pio.write_image(fig, constants.MANHATTAN_MAP_FILE_PATH)


# @asset(
#     deps=["taxi_trips"]
# )
# def trips_by_week(database: DuckDBResource) -> None:


#     current_date = datetime.strptime("2023-03-01", constants.DATE_FORMAT)
#     end_date = datetime.strptime("2023-04-01", constants.DATE_FORMAT)

#     result = pd.DataFrame()
#     #conn = duckdb.connect(os.getenv("DUCKDB_DATABASE"))
#     conn = database.get_connection()

#     while current_date < end_date:
#         current_date_str = current_date.strftime(constants.DATE_FORMAT)
#         query = f"""
#             select
#                 vendor_id, total_amount, trip_distance, passenger_count
#             from trips
#             where date_trunc('week', pickup_datetime) = date_trunc('week', '{current_date_str}'::date)
#         """

#         data_for_week = conn.execute(query).fetch_df()

#         aggregate = data_for_week.agg({
#             "vendor_id": "count",
#             "total_amount": "sum",
#             "trip_distance": "sum",
#             "passenger_count": "sum"
#         }).rename({"vendor_id": "num_trips"}).to_frame().T # type: ignore

#         aggregate["period"] = current_date

#         result = pd.concat([result, aggregate])

#         current_date += timedelta(days=7)

#     # clean up the formatting of the dataframe
#     result['num_trips'] = result['num_trips'].astype(int)
#     result['passenger_count'] = result['passenger_count'].astype(int)
#     result['total_amount'] = result['total_amount'].round(2).astype(float)
#     result['trip_distance'] = result['trip_distance'].round(2).astype(float)
#     result = result[["period", "num_trips", "total_amount", "trip_distance", "passenger_count"]]
#     result = result.sort_values(by="period")

#     result.to_csv(constants.TRIPS_BY_WEEK_FILE_PATH, index=False)





@asset(
    deps=["taxi_trips"],
    partitions_def=weekly_partition
)
def trips_by_week(context: AssetExecutionContext, database: DuckDBResource) -> None:
    """
      The number of trips per week, aggregated by week.
    """

    period_to_fetch = context.partition_key

    # get all trips for the week
    query = f"""
        select vendor_id, total_amount, trip_distance, passenger_count
        from trips
        where pickup_datetime >= '{period_to_fetch}'
            and pickup_datetime < '{period_to_fetch}'::date + interval '1 week'
    """

    with database.get_connection() as conn:
        data_for_month = conn.execute(query).fetch_df()

    aggregate = data_for_month.agg({
        "vendor_id": "count",
        "total_amount": "sum",
        "trip_distance": "sum",
        "passenger_count": "sum"
    }).rename({"vendor_id": "num_trips"}).to_frame().T # type: ignore

    # clean up the formatting of the dataframe
    aggregate["period"] = period_to_fetch
    aggregate['num_trips'] = aggregate['num_trips'].astype(int)
    aggregate['passenger_count'] = aggregate['passenger_count'].astype(int)
    aggregate['total_amount'] = aggregate['total_amount'].round(2).astype(float)
    aggregate['trip_distance'] = aggregate['trip_distance'].round(2).astype(float)
    aggregate = aggregate[["period", "num_trips", "total_amount", "trip_distance", "passenger_count"]]

    try:
        # If the file already exists, append to it, but replace the existing month's data
        existing = pd.read_csv(constants.TRIPS_BY_WEEK_FILE_PATH)
        existing = existing[existing["period"] != period_to_fetch]
        existing = pd.concat([existing, aggregate]).sort_values(by="period")
        existing.to_csv(constants.TRIPS_BY_WEEK_FILE_PATH, index=False)
    except FileNotFoundError:
        aggregate.to_csv(constants.TRIPS_BY_WEEK_FILE_PATH, index=False)
