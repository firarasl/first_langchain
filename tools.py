
import os
import ast
#from langchain_community.embeddings import OllamaEmbeddings
from langchain_ollama import OllamaEmbeddings

from langchain_community.vectorstores import FAISS
from langchain_community.agent_toolkits import SQLDatabaseToolkit
#from langchain.agents.agent_toolkits import create_retriever_tool
from langchain_core.tools import create_retriever_tool
from langchain_google_community import GooglePlacesTool
from langchain.tools import BaseTool
from pydantic import BaseModel, Field
from googlemaps import Client as GoogleMaps


gmaps = GoogleMaps(api_key=os.environ["GOOGLE_MAPS_API_KEY"])
database_schema = db.get_table_info()

class DirectionsInput(BaseModel):
    origin: str = Field(..., description="The starting address for directions.")
    destination: str = Field(..., description="The destination address for directions.")

class GeocodingTool(BaseTool):
    name = "google_maps_geocoding"
    description = "Use this tool to get the latitude and longitude of a given address using Google Maps Geocoding API."

    def _run(self, address):
        try:
            geocode_result = gmaps.geocode(address)
            if geocode_result:
                location = geocode_result[0]['geometry']['location']
                print("--- Geocoding Result ---")
                print(f"Address: {address}")
                print(f"Location: {location}")
                print("--- Geocoding Result End ---")
                return f"The coordinates for the address '{address}' are: Latitude: {location['lat']}, Longitude: {location['lng']}."
            return "Unable to find coordinates for the provided address."
        except Exception as e:
            print(f"Error during geocoding: {e}")
            return "An error occurred while trying to get the coordinates."

class DirectionsTool(BaseTool):
    name = "google_maps_directions"
    description = "Use this tool to get directions between two addresses using Google Maps Directions API."
    args_schema = DirectionsInput

    def _run(self, origin, destination):
        try:
            print("DIRECTIONS API: Origin:", origin, "Destination:", destination)
            directions_result = gmaps.directions(origin, destination, mode="driving")
            if directions_result:
                distance = directions_result[0]['legs'][0]['distance']['text']
                duration = directions_result[0]['legs'][0]['duration']['text']
                return f"The travel distance from '{origin}' to '{destination}' is {distance} and it will take approximately {duration} by car."
            return "Unable to find directions for the provided addresses."
        except Exception as e:
            print(f"Error during getting directions: {e}")
            return "An error occurred while trying to get the directions."


directions_tool = DirectionsTool()
google_maps_geocoding_tool = GeocodingTool()
google_places = GooglePlacesTool()

#def query_as_list(db, query):
#    res = db.run(query)                  
#    rows = ast.literal_eval(res)         
#    # unpack each tuple, drop NULLs/empties, force everything to str
#    return list({str(el).strip() for row in rows for el in row if el})
    
def query_as_list(db, query):
    res = db.run(query)
    res = [el for sub in ast.literal_eval(res) for el in sub if el]
    res = [re.sub(r"\b\d+\b", "", string).strip() for string in res]
    return list(set(res))


def setup_tools(db, llm):

    addresses = query_as_list(db, "SELECT address FROM core_condobuilding")
    alt_names = query_as_list(db, "SELECT alt_name FROM core_condobuilding")
    embeddings = OllamaEmbeddings(model="nomic-embed-text")
    # embeddings = OllamaEmbeddings(model="llama3.1", temperature=0)
    vector_db = FAISS.from_texts(alt_names + addresses, embeddings)
    retriever = vector_db.as_retriever(search_type="similarity", search_kwargs={"k": 3})
    description = """ Use to look up values to filter on. Input is an approximate spelling of the proper noun, output is valid proper nouns. Use the nouns most similar to the search. """
    retrieve_tool = create_retriever_tool(retriever, name ="search_proper_nouns", description=description)

    toolkit = SQLDatabaseToolkit(db=db, llm=llm)
    tools = toolkit.get_tools()
    tools.append(retrieve_tool)
    tools.append(google_maps_geocoding_tool)
    tools.append(directions_tool)
    tools.append(google_places)
    return tools
