from django.db import models
from django.db.models.query import QuerySet
from localflavor.us.models import USStateField

from geopy.units import nautical, degrees
import geopy.distance

from loci.utils import geocode


class PlaceManager(models.Manager):
    def get_queryset(self):
        return PlaceQuerySet(self.model, using=self.db)

    def near(self, *args, **kwargs):
        return self.get_queryset().near(*args, **kwargs)

    def near_distances(self, *args, **kwargs):
        return self.get_queryset().near_distances(*args, **kwargs)


class PlaceQuerySet(QuerySet):
    def near(self, location, distance=None):
        """
        Returns a list of items in the QuerySet which are within the given
        distance of the given location. Does NOT return a QuerySet.

        Accepts either a Place instance or a (lat, lon) tuple for location.
        Also accepts a Place instance with a nearby_distance attribute added
        (as returned from utils.geolocate_request); in this case, distance need
        not be explicitly passed.

        """

        # figure out if we received an object or tuple and get the location
        try:
            (latitude, longitude) = location.location
        except AttributeError:
            (latitude, longitude) = location

        # make sure we have a valid location
        if not (latitude and longitude):
            return []

        # get the passed distance or attached to Place
        if distance is None:
            try:
                distance = location.nearby_distance
            except AttributeError:
                raise ValueError('Distance must be attached or passed explicitly.')

        # prune down the set of places before checking precisely
        # deg_lat = Decimal(str(degrees(arcminutes=nautical(miles=distance))))
        deg_lat = degrees(arcminutes=nautical(miles=distance))
        lat_range = (latitude - deg_lat, latitude + deg_lat)
        long_range = (longitude - deg_lat * 2, longitude + deg_lat * 2)
        queryset = self.filter(
            latitude__range=lat_range,
            longitude__range=long_range
        )

        locations = []
        for location in queryset:
            if location.latitude and location.longitude:
                exact_distance = geopy.distance.distance(
                    (latitude, longitude),
                    (location.latitude, location.longitude)
                )
                # print 'exact_distance ', exact_distance.miles
                if exact_distance.miles <= distance:
                    locations.append(location)
        return locations

    def near_distances(self, location, distance):
        location_distances = {}
        near_locations = PlaceQuerySet.near(self, location, distance)

        try:
            (latitude, longitude) = location.location
        except AttributeError:
            (latitude, longitude) = location

        for l in near_locations:
            if l.latitude and l.longitude:
                exact_distance = geopy.distance.distance(
                    (l.latitude, l.longitude),
                    (latitude, longitude)
                )
            location_distances[l] = "{0:.2f}".format(round(exact_distance.miles, 2))
        return location_distances


class Place(models.Model):
    name = models.CharField(max_length=200)
    address = models.CharField(max_length=180, blank=True, default=' ')
    city = models.CharField(max_length=50, blank=True, default=' ')
    state = USStateField(blank=True, default=' ')
    zip_code = models.CharField(max_length=10, blank=True, default=' ')

    latitude = models.FloatField(null=True, blank=True, default=None, db_index=True)
    longitude = models.FloatField(null=True, blank=True, default=None, db_index=True)

    objects = PlaceManager()

    def __unicode__(self):
        return u'%s (%s, %s)' % (self.name, self.latitude, self.longitude)

    def save(self, *args, **kwargs):

        if not self.city and not self.state and not self.zip_code:
            super(Place, self).save(*args, **kwargs)
            return ''
        if self.city == ' ' and self.state == ' ' and self.zip_code == ' ':
            super(Place, self).save(*args, **kwargs)
            return ''

        # Latitude/longitude are not set, trying geocode
        if not all(self.location):
            geoloc = geocode(self.full_address)
            if all(geoloc.location):
                (self.latitude, self.longitude) = geoloc.location

        if not self.city:
            self.city = geoloc.city
        if not self.state:
            self.state = geoloc.state
        if not self.zip_code:
            self.zip_code = geoloc.zip_code

        super(Place, self).save(*args, **kwargs)

    def distance_to(self, latitude, longitude):
        return geopy.distance.distance(
            (latitude, longitude),
            self.location,
        )

    @property
    def full_address(self):
        parts = []
        if self.address:
            parts.append(self.address + ',')
        if self.city:
            parts.append(self.city)
        if self.state:
            parts.append(self.state)
        if self.zip_code:
            parts.append(self.zip_code)
        return ' '.join(parts)

    @property
    def location(self):
        return (self.latitude, self.longitude)

    @location.setter
    def location(self, point):
        (self.latitude, self.longitude) = point
