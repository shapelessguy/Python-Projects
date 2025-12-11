import { useState } from "react";
import "./App.css"


const categories: Array<Record<string, any>> = [
  {
    name: "Pasta",
    url: "/images/pasta.jpg",
    children: [
      { name: "Carbonara", url: "", vote: 6 },
      { name: "Pasta with lentils", url: "", vote: 7 },
      { name: "Pasta with chickpeas", url: "", vote: 7 },
      { name: "Pasta with beans", url: "", vote: 7 },
      { name: "Pasta arrabbiata", url: "", vote: 8 },
      { name: "Pasta with peas", url: "", vote: 8 },
      { name: "Ravioli", url: "", vote: 8 },
      { name: "Spaghetti aglio e olio", url: "", vote: 8 },
      { name: "Spaghetti e vongole", url: "", vote: 9 },
      { name: "Spaghetti e cozze", url: "", vote: 9 },
      { name: "Cacio e pepe", url: "", vote: 9 },
      { name: "Amatriciana", url: "", vote: 9 },
      { name: "Lasagna", url: "", vote: 9 },
      { name: "Genovese", url: "", vote: 10 },
    ]
  },
  {
    name: "Dough",
    url: "/images/dough.jpg",
    children: [
      { name: "Doener", url: "", vote: 7 },
      { name: "Pizza", url: "", vote: 8 },
      { name: "Burger", url: "", vote: 8 },
    ]
  },
  {
    name: "Risotti",
    url: "/images/risotti.jpg",
    children: [
      { name: "Risotto with provola", url: "", vote: 7 },
      { name: "Risotto with shrimps", url: "", vote: 8 },
    ]
  },
  {
    name: "Meat",
    url: "/images/meat.jpg",
    children: [
      { name: "Fried Chicken", url: "", vote: 5 },
      { name: "Chicken Schnitzel", url: "", vote: 6 },
      { name: "Chicken and potatoes", url: "", vote: 8 },
      { name: "Scaloppina al limone", url: "", vote: 8 },
      { name: "Steak", url: "", vote: 9 },
    ]
  },
  {
    name: "Fish",
    url: "/images/fish.jpg",
    children: [
      { name: "Sushi", url: "", vote: 10 },
    ]
  },
  {
    name: "Desserts",
    url: "/images/desserts.jpg",
    children: [
      { name: "Cheesecake", url: "", vote: 5 },
      { name: "Tiramisu", url: "", vote: 6 },
      { name: "Pannacotta", url: "", vote: 8 },
      { name: "Crepes", url: "", vote: 9 },
    ]
  },
  {
    name: "Restaurants",
    url: "/images/restaurant.jpg",
    children: [
      { name: "My Chicken", url: "", vote: 4 },
      { name: "Mc Donalds", url: "", vote: 5 },
      { name: "Burger King", url: "", vote: 6 },
      { name: "Vietnamese", url: "", vote: 7 },
    ]
  }
];

export default function Dishes() {
  const [category, setCategory] = useState<string>("");
  const [random, setRandom] = useState<any>({ name: "", url: "", special: "randomize" });
  
  function getCategories() {
    if (random.name !== "") setRandom({ name: "", url: "", special: "randomize" });
    return categories.map((categ, index) => {
      const isEven = index % 2 === 0;
      return (
        <div
          key={index}
          style={{
            display: "flex",
            flexDirection: isEven ? "row" : "row-reverse",
            alignItems: "center",
            justifyContent: "space-between",
            gap: "20px",
            background: "rgba(0, 0, 0, 0.52)",
            padding: "15px",
            borderRadius: "10px",
            boxShadow: "0 2px 8px rgba(0,0,0,0.1)",
            cursor: "pointer",
            userSelect: "none",
          }}
          onClick={() => setCategory(categ.name)}
        >
          <img
            src={
              categ.url !== ""
                ? categ.url
                : `/images/${categ.name.toLowerCase()}.jpg`
            }
            alt={categ.name}
            className={`imgStyle ${window.innerWidth > 800? "": "small"}`}
          />
          <h2
            style={{
              flex: 1,
              textAlign: isEven ? "left" : "right",
              margin: 0,
            }}
          >
            {categ.name}
          </h2>
        </div>
      );
    })
  }

  function getRandomInt(min: number, max: number): number {
    return Math.floor(Math.random() * (max - min + 1)) + min;
  }

  const getStars = (value: number) => {
    const full = Math.floor(value);
    if (!full) return "";
    return "★".repeat(full) + ` (${full})`;
  };

  function getDishes(category: string) {
    let dishesList = categories.find((e: any) => e.name === category);
    if (!dishesList || !dishesList.children) return (<></>);
    else {
      const dishesList_: Array<Record<string, any>> = [
        { name: "Back", url: "/images/back.png", special: "back" },
        random,
      ].concat(dishesList.children.map((e: any) => e));
      return dishesList_.map((dish, index) => {
          const isEven = index % 2 === 0;
          return (
            <div
              key={index}
              style={{
                display: "flex",
                flexDirection: isEven ? "row" : "row-reverse",
                alignItems: "center",
                justifyContent: "space-between",
                gap: "20px",
                background: "rgba(0, 0, 0, 0.52)",
                padding: "15px",
                borderRadius: "10px",
                boxShadow: "0 2px 8px rgba(0,0,0,0.1)",
                userSelect: dish.special? "none": "auto",
                cursor: dish.special? "pointer": "default",
              }}
              onClick={() => {
                if (dish.name === "Back") setCategory("");
                else if (dish.special === "randomize") {
                  const randNum = getRandomInt(2, dishesList_.length)
                  setRandom({ name: dishesList_[randNum].name, url: dishesList_[randNum].url, special: "randomize" });
                }
              }}
            >
              <img
                src={dish.url !== ""? dish.url: `/images/${dish.name.toLowerCase()}.jpg`}
                alt={dish.name}
                className={`imgStyle ${window.innerWidth > 800? "": "small"}`}
              />
              <h2
                style={{
                  flex: 1,
                  textAlign: isEven ? "left" : "right",
                  margin: 0,
                }}
              >
                <div style={{display: "flex", flexDirection: "column"}}>
                  <label>
                    {dish.special === "randomize"? "Random: ": ""}{dish.name}
                  </label>
                  <label>
                    {getStars(dish.vote)}
                  </label>
                </div>
              </h2>
            </div>
          );
        })
      }
  }
  

  return (
    <div
      style={{
        display: "flex",
        flexDirection: "column",
        padding: "20px",
        fontFamily: "sans-serif",
        height: "100vh",
        boxSizing: "border-box",
        overflowY: "auto",
        margin: 0,
      }}
    >
      <h1 style={{ textAlign: "center", marginBottom: "40px" }}>{category !== ""? `Category: ${category}`: `Our dishes`}</h1>

      <div
        style={{
          display: "grid",
          gridTemplateColumns: window.innerWidth > 800? "1fr 1fr": "1fr",
          gap: "40px 20px",
          paddingBottom: "40px",
        }}
      >
        {category === "" && getCategories()}
        {category !== "" && getDishes(category)}
        
      </div>
    </div>
  );
}