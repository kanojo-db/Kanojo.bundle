KANOJO_BASE_URL = 'https://kanojodb.com%s'

# Movies
KANOJO_MOVIE_SEARCH = '/api/v1/search?q=%s'
KANOJO_MOVIE = '/api/v1/movie/%s'

ARTWORK_ITEM_LIMIT = 15
# How much weight to give ratings vs. vote counts when picking best posters. 0 means use only ratings.
POSTER_SCORE_RATIO = .3
BACKDROP_SCORE_RATIO = .3
STILLS_SCORE_RATIO = .3

####################################################################################################


def Start():

    pass


####################################################################################################


def GetKanojoJSON(url, cache_time=CACHE_1HOUR):
  kanojo_dict = None

  try:
    kanojo_dict = JSON.ObjectFromURL(KANOJO_BASE_URL % url, sleep=2.0, headers={'Accept': 'application/json'}, cacheTime=cache_time)
  except Exception as e:
    Log('Error fetching JSON from Kanojo: %s' % (KANOJO_BASE_URL % url))
    Log(e)

  return kanojo_dict


####################################################################################################


def AppendSearchResult(results, id, name=None, year=-1, score=0, lang=None):

    new_result = dict(id=str(id), name=name, year=int(year),
                      score=score, lang=lang)

    if isinstance(results, list):

        results.append(new_result)

    else:

        results.Append(MetadataSearchResult(**new_result))

####################################################################################################


def DictToMovieMetadataObj(metadata_dict, metadata):

    try:
        if not metadata or not metadata.attrs:
            return
    except AttributeError:
        # TODO: add a more official log message about version number when available
        Log('WARNING: Framework not new enough to use One True Agent')
        return

    for attr_name, attr_obj in metadata.attrs.iteritems():

        if attr_name not in metadata_dict:
            continue

        dict_value = metadata_dict[attr_name]

        if isinstance(dict_value, list):

            attr_obj.clear()
            for val in dict_value:
                attr_obj.add(val)

        elif isinstance(dict_value, dict):

            # Can't access MapObject, so have to write these out
            if attr_name in ['posters', 'art', 'themes']:

                for k, v in dict_value.iteritems():
                    if isinstance(v, tuple):
                        try:
                            attr_obj[k] = Proxy.Preview(
                                HTTP.Request(v[0]).content, sort_order=v[1])
                        except:
                            pass
                    else:
                        attr_obj[k] = v

                attr_obj.validate_keys(dict_value.keys())

            else:
                for k, v in dict_value.iteritems():
                    attr_obj[k] = v

        elif attr_name is 'originally_available_at':

            try:
                attr_obj.setcontent(Datetime.ParseDate(dict_value).date())
            except:
                pass

        else:
            attr_obj.setcontent(dict_value)

    # The following are special kind of objects
    if 'roles' in metadata_dict:
        metadata.roles.clear()
        for role in metadata_dict['roles']:
            meta_role = metadata.roles.new()
            if 'role' in role:
                meta_role.role = role['role']
            if 'name' in role:
                meta_role.name = role['name']
            if 'photo' in role:
                meta_role.photo = role['photo']


####################################################################################################
def PerformKanojoMovieSearch(results, media, lang):
        # Replace spaces in the title (a product code) with dashes, since Plex's scanner removes them
        kanojo_dict = GetKanojoJSON(url=KANOJO_MOVIE_SEARCH % (
            media.name.replace(' ', '-')))

        if isinstance(kanojo_dict, list):
            for _, movie in enumerate(kanojo_dict):
                score = 100
                # Multiply the Levenshtein Distance by 10 to account for how short product codes are.
                score = score - \
                    abs(String.LevenshteinDistance(
                        movie['dvd_id'].lower(), media.name.replace(' ', '-').lower())) * 50

                if 'release_date' in movie and movie['release_date']:
                    release_year = int(movie['release_date'].split('-')[0])
                else:
                    release_year = -1

                if media.year and int(media.year) > 1900 and release_year:
                    year_diff = abs(int(media.year) - release_year)

                    if year_diff <= 1:
                        score = score + 10
                    else:
                        score = score - (5 * year_diff)

                Log('Score: %d' % score)
                if score <= 0:
                    continue
                else:
                    # If lang is English, get the English title, otherwise use the original title.
                    if lang == Locale.Language.English:
                        name = movie['original_title']
                    else:
                        name = movie['title']

                    AppendSearchResult(results=results,
                                        id=movie['id'],
                                        name="[{0}] {1}".format(movie['dvd_id'], name),
                                        year=release_year,
                                        score=score,
                                        lang=lang)

####################################################################################################


def PerformKanojoMovieUpdate(metadata_id, lang, existing_metadata):
    metadata = dict(id=metadata_id)

    kanojo_dict = GetKanojoJSON(url=KANOJO_MOVIE % (metadata_id))

    if not isinstance(kanojo_dict, dict):
        return None

    # Rating.
    # votes = kanojo_dict.get('vote_count') or 0
    # rating = kanojo_dict.get('vote_average') or 0.0
    # if votes > 3:
    #    metadata['rating'] = rating
    #    metadata['audience_rating'] = 0.0
    #    metadata['rating_image'] = None
    #    metadata['audience_rating_image'] = None

    dvd_code = kanojo_dict.get('dvd_id')

    # If there is a title, use that, otherwise use the original title.
    if 'title' in kanojo_dict and kanojo_dict['title'] is not None and kanojo_dict['title'] != '':
        # Titles should be as follows: [DVD Code] Title
        metadata['title'] = "[{0}] {1}".format(dvd_code, kanojo_dict['title'])
    else:
        metadata['title'] = "[{0}] {1}".format(dvd_code, kanojo_dict['original_title'])

    if 'original_title' in kanojo_dict and kanojo_dict['original_title'] != metadata['title']:
        metadata['original_title'] = kanojo_dict['original_title']

    # Release date.
    if 'release_date' in kanojo_dict and kanojo_dict['release_date']:
        metadata['originally_available_at'] = kanojo_dict['release_date']
        metadata['year'] = Datetime.ParseDate(
            kanojo_dict['release_date']).date().year

    # If runtime is available, is a number, and is greater than 0, set the duration.
    if 'runtime' in kanojo_dict and kanojo_dict['runtime'] is not None and int(kanojo_dict['runtime']) > 0:
        metadata['duration'] = int(kanojo_dict['runtime']) * 60 * 1000

    # Genres.
    # metadata['genres'] = []
    # for genre in (kanojo_dict.get('genres') or list()):
    #    metadata['genres'].append(genre.get('name', '').strip())

    #metadata['collections'] = []
    if 'series' in kanojo_dict and kanojo_dict['series'] != None:
        # Check if there is a translation available, if not, use the original name.
        if kanojo_dict['series']['name'] is not None and kanojo_dict['series']['name'] != '':
            metadata['collections'] = [kanojo_dict['series']['name']]
        else:
            metadata['collections'] = [kanojo_dict['series']['original_name']]

    # Studio.
    if 'studio' in kanojo_dict and kanojo_dict['studio'] is not None:
        if 'name' in kanojo_dict['studio'] and kanojo_dict['studio']['name'] is not None and kanojo_dict['studio']['name'] != '':
            metadata['studio'] = kanojo_dict['studio']['name']
        else:
            metadata['studio'] = kanojo_dict['studio']['original_name']

    # Country.
    metadata['countries'] = ['Japan']

    # Cast.
    metadata['roles'] = list()

    if 'roles' in kanojo_dict and kanojo_dict['roles'] is not None:
        for member in kanojo_dict.get('roles') or list():
                role = dict()
                if 'name' in member and member['name'] is not None and member['name'] != '':
                    role['name'] = member['name']
                else:
                    role['name'] = member['original_name']

                # Since models basically always play themselves, we'll use their age as the role.
                # If member has an age_string, use that as the role.
                if 'age_string' in member and member['age_string'] is not None and member['age_string'] != '':
                    role['role'] = member['age_string']

                if 'profile_url' in member and member['profile_url'] is not None:
                    role['photo'] = member['profile_url']
                
                metadata['roles'].append(role)

    metadata['posters'] = dict()
    if 'thumb_url' in kanojo_dict and kanojo_dict['thumb_url'] is not None:
        metadata['posters'][kanojo_dict['thumb_url']] = Proxy.Media(HTTP.Request(kanojo_dict['thumb_url']).content)

    # Backdrops.
    metadata['art'] = dict()
    if 'art_url' in kanojo_dict and kanojo_dict['art_url'] is not None:
        metadata['art'][kanojo_dict['art_url']] = Proxy.Media(HTTP.Request(kanojo_dict['art_url']).content)

    return metadata

####################################################################################################


class KanojoAgent(Agent.Movies):

    name = 'Kanojo'
    languages = [Locale.Language.English, Locale.Language.Japanese]
    primary_provider = True
    accepts_from = ['com.plexapp.agents.localmedia']

    def search(self, results, media, lang, manual):

        PerformKanojoMovieSearch(results, media, lang)

    def update(self, metadata, media, lang):

        metadata_dict = PerformKanojoMovieUpdate(metadata.id, lang, metadata)

        if metadata_dict is None:
            Log('Kanojo was unable to get any metadata for %s (lang = %s)' %
                (metadata.id, lang))
            return

        DictToMovieMetadataObj(metadata_dict, metadata)

####################################################################################################


class FakeMediaObj():

    def __init__(self, id, name, year):
        self.name = name
        self.year = year
        self.primary_metadata = FakePrimaryMetadataObj(id)

####################################################################################################


class FakePrimaryMetadataObj():

    def __init__(self, id):
        self.id = id
