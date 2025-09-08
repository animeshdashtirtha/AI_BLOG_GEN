//             color changer

// var red=document.querySelector("#red");
// var blue=document.querySelector("#blue");
// var yellow=document.querySelector("#yellow");
// var white=document.querySelector("#white");
// var purple=document.querySelector("#purple");
// var target=document.querySelector('#target');

// const colorchanger=(color) => {

//     color.addEventListener("click", () => {
//     target.style.backgroundColor=window.getComputedStyle(color).backgroundColor;
//     })
//     }

// colorchanger(red);
// colorchanger(blue);
// colorchanger(purple);
// colorchanger(yellow);
// colorchanger(white);

var employees = [
    { name: "Tirtha", id: "123" },
    { name: "Miraz", id: "234" },
    { name: "rumi", id: "845" },
    {name: "opu", id: "491"},
    {name: "roni", id: "012"},
];

var button_for_list = document.querySelector("#button_for_list");
var listbox = document.querySelector("#listbox");
var loginform= document.querySelector("#loginform");
const button_for_sort=document.querySelector("#sortlist")



var create_loginList = () => 
    {
    let index = 0;  // Track the index of the current employee to display
    button_for_list.addEventListener("click", (e) => 
        {
        if (index < employees.length) 
        {  // Only add employees if available
            const div = document.createElement("div");
            div.classList.add("loginclass")
            const emp_ins = document.createTextNode(`The name is ${employees[index].name} and the id is ${employees[index].id}`)  
          
            div.appendChild(emp_ins);
            listbox.appendChild(div);
            index++;  // Increment the index to show the next employee on the next click
        }

        else if(index >= employees.length)
            {button_for_sort.addEventListener("click",(e)=>{
            //clear list;
            listbox.innerHTML=""
            
            // sort list
            const sortedEmployees = employees.sort((a, b) => Number(b.id) - Number(a.id));
            sortedEmployees.forEach((i)=>{

                const div = document.createElement("div");
                div.classList.add("loginclass")
                const emp_ins = document.createTextNode(`The name is ${i.name} and the id is ${i.id}`)
                div.appendChild(emp_ins);
                listbox.appendChild(div);
            })
            e.preventDefault()})}
            
            e.preventDefault();
            // click event stopper of sort list button
            button_for_sort.addEventListener("click",(e)=>{
            e.preventDefault();   
            })
        })
    }

    

  create_loginList()