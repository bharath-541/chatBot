from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional
import logging

logger = logging.getLogger(__name__)

class Tool(ABC):
    """Abstract base class for all tools"""
    
    @property
    @abstractmethod
    def name(self) -> str:
        pass
    
    @property
    @abstractmethod
    def description(self) -> str:
        pass
    
    @abstractmethod
    async def execute(self, **kwargs) -> Dict[str, Any]:
        pass

class HospitalSearchTool(Tool):
    """Tool for searching nearby hospitals"""
    
    def __init__(self, api_key: str):
        if not api_key:
            raise ValueError("Google Maps API key is required")
        self.api_key = api_key
    
    @property
    def name(self) -> str:
        return "hospital_search"
    
    @property
    def description(self) -> str:
        return """Search for nearby hospitals. 
        
Usage examples:
- By place name: {"tool": "hospital_search", "params": {"place": "Boston"}}
- By coordinates: {"tool": "hospital_search", "params": {"latitude": 40.7128, "longitude": -74.0060}}

Returns hospital names, addresses, ratings, and status."""
    
    async def _geocode_place(self, place_name: str) -> Optional[tuple]:
        """Convert place name to coordinates using Google Places API Text Search"""
        try:
            import httpx
            
            logger.info(f"Searching for place: {place_name}")
            
            # Use Places API (New) - Text Search to find the place
            url = "https://places.googleapis.com/v1/places:searchText"
            
            headers = {
                "Content-Type": "application/json",
                "X-Goog-Api-Key": self.api_key,
                "X-Goog-FieldMask": "places.location,places.displayName"
            }
            
            payload = {
                "textQuery": place_name
            }
            
            async with httpx.AsyncClient() as client:
                response = await client.post(url, json=payload, headers=headers, timeout=5.0)
                response.raise_for_status()
                data = response.json()
            
            if data.get("places") and len(data["places"]) > 0:
                location = data["places"][0]["location"]
                lat = location["latitude"]
                lng = location["longitude"]
                place_display = data["places"][0].get("displayName", {}).get("text", place_name)
                logger.info(f"Found '{place_display}' at ({lat}, {lng})")
                return (lat, lng)
            else:
                logger.warning(f"Could not find place: {place_name}")
                return None
                
        except Exception as e:
            logger.error(f"Place search error: {e}")
            return None
    
    async def execute(self, latitude: float = None, longitude: float = None, place: str = None, query: str = None, location: str = None, radius: int = 5000, **kwargs) -> Dict[str, Any]:
        """Execute hospital search with either coordinates or place name"""
        # Handle various input formats
        place_name = place or query or location or kwargs.get('address') or kwargs.get('place_name')
        
        logger.info(f"Hospital search called: lat={latitude}, lng={longitude}, place={place_name}")
        
        # If place name provided, geocode it first
        if place_name and not latitude and not longitude:
            coords = await self._geocode_place(place_name)
            if coords:
                latitude, longitude = coords
            else:
                return {
                    "success": False,
                    "error": f"Could not find location for: {place_name}",
                    "message": "Please provide valid coordinates or a known place name"
                }
        
        # Validate we have coordinates
        if latitude is None or longitude is None:
            return {
                "success": False,
                "error": "Missing location information",
                "message": "Please provide either coordinates (latitude, longitude) or a place name"
            }
        
        return await self._execute_real(latitude, longitude, radius)
    
    async def _execute_real(self, latitude: float, longitude: float, radius: int) -> Dict[str, Any]:
        """Real implementation using Google Places API (New)"""
        try:
            import httpx
            
            logger.info(f"[REAL] Searching hospitals near ({latitude}, {longitude}) within {radius}m")
            
            # Use new Places API (New) - Text Search
            url = "https://places.googleapis.com/v1/places:searchNearby"
            
            headers = {
                "Content-Type": "application/json",
                "X-Goog-Api-Key": self.api_key,
                "X-Goog-FieldMask": "places.displayName,places.formattedAddress,places.rating,places.currentOpeningHours,places.location"
            }
            
            payload = {
                "includedTypes": ["hospital"],
                "maxResultCount": 5,
                "locationRestriction": {
                    "circle": {
                        "center": {
                            "latitude": latitude,
                            "longitude": longitude
                        },
                        "radius": float(radius)
                    }
                }
            }
            
            async with httpx.AsyncClient() as client:
                response = await client.post(url, json=payload, headers=headers, timeout=10.0)
                response.raise_for_status()
                data = response.json()
            
            hospitals = []
            for place in data.get('places', []):
                hospital_info = {
                    "name": place.get('displayName', {}).get('text', 'Unknown'),
                    "address": place.get('formattedAddress', 'N/A'),
                    "rating": place.get('rating', 'N/A'),
                    "open_now": place.get('currentOpeningHours', {}).get('openNow', False),
                    "location": place.get('location', {})
                }
                hospitals.append(hospital_info)
            
            logger.info(f"[REAL] Found {len(hospitals)} hospitals")
            
            return {
                "success": True,
                "mode": "real",
                "hospitals": hospitals,
                "count": len(hospitals)
            }
        
        except Exception as e:
            logger.error(f"Error executing hospital search: {e}")
            return {
                "success": False,
                "error": str(e),
                "message": "Failed to search hospitals. Please try again."
            }

class ToolRegistry:
    """Registry for managing all available tools"""
    
    def __init__(self):
        self.tools: Dict[str, Tool] = {}
    
    def register(self, tool: Tool):
        self.tools[tool.name] = tool
        logger.info(f"Registered tool: {tool.name}")
    
    def get_tool(self, name: str) -> Optional[Tool]:
        return self.tools.get(name)
    
    def get_all_tools(self) -> List[Tool]:
        return list(self.tools.values())
    
    def get_tool_descriptions(self) -> List[Dict[str, str]]:
        return [
            {"name": tool.name, "description": tool.description}
            for tool in self.tools.values()
        ]
